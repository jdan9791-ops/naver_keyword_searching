"""
Google Drive 연동 모듈.

인증 방식: OAuth2 (credentials.json → token.json)
  1. Google Cloud Console에서 OAuth 2.0 클라이언트 ID 생성 후 credentials.json 다운로드
  2. 첫 실행 시 브라우저 인증 → token.json 자동 저장
  3. 이후 실행은 token.json으로 자동 인증

폴더 구조 (Google Drive):
  [GOOGLE_DRIVE_ROOT_FOLDER_ID]/
    └── {keyword}/
          ├── results.json
          ├── scam_urls.txt
          └── report.json
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

_MIME_FOLDER = "application/vnd.google-apps.folder"
_MIME_JSON = "application/json"
_MIME_TEXT = "text/plain"


def _mime_for(filename: str) -> str:
    if filename.endswith(".json"):
        return _MIME_JSON
    return _MIME_TEXT


class GoogleDriveManager:
    """
    Google Drive 파일/폴더 관리 클래스.

    Parameters
    ----------
    credentials_file : str | Path
        OAuth2 credentials.json 경로
    token_file : str | Path
        인증 토큰 저장 경로 (자동 생성)
    root_folder_id : str | None
        업로드할 Google Drive 루트 폴더 ID (None이면 내 드라이브 최상위)
    """

    def __init__(
        self,
        credentials_file: str | Path,
        token_file: str | Path = "token.json",
        root_folder_id: str | None = None,
    ) -> None:
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self.root_folder_id = root_folder_id
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google Drive 라이브러리가 설치되지 않았습니다.\n"
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )

        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"credentials.json 파일이 없습니다: {self.credentials_file}\n"
                        "Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 생성하고 "
                        "credentials.json을 프로젝트 폴더에 저장하세요."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            with self.token_file.open("w") as f:
                f.write(creds.to_json())
            logger.info("Google Drive 인증 완료, 토큰 저장: %s", self.token_file)

        self._service = build("drive", "v3", credentials=creds)
        return self._service

    def get_or_create_folder(self, name: str, parent_id: str | None = None) -> str:
        """Drive에서 폴더를 찾거나 없으면 생성. 폴더 ID 반환."""
        service = self._get_service()
        parent = parent_id or self.root_folder_id

        query_parts = [
            f"name = '{name}'",
            f"mimeType = '{_MIME_FOLDER}'",
            "trashed = false",
        ]
        if parent:
            query_parts.append(f"'{parent}' in parents")

        result = (
            service.files()
            .list(q=" and ".join(query_parts), fields="files(id, name)")
            .execute()
        )
        files = result.get("files", [])
        if files:
            return files[0]["id"]

        metadata = {"name": name, "mimeType": _MIME_FOLDER}
        if parent:
            metadata["parents"] = [parent]

        folder = service.files().create(body=metadata, fields="id").execute()
        logger.info("Drive 폴더 생성: %s (id=%s)", name, folder["id"])
        return folder["id"]

    def _find_file(self, name: str, parent_id: str) -> str | None:
        """Drive 폴더 안에서 파일 ID 검색."""
        service = self._get_service()
        query = (
            f"name = '{name}' and '{parent_id}' in parents and trashed = false"
        )
        result = service.files().list(q=query, fields="files(id)").execute()
        files = result.get("files", [])
        return files[0]["id"] if files else None

    def upload_file(self, local_path: Path, folder_id: str) -> str:
        """로컬 파일을 Drive 폴더에 업로드(이미 있으면 덮어씀). 파일 ID 반환."""
        from googleapiclient.http import MediaFileUpload

        service = self._get_service()
        mime = _mime_for(local_path.name)
        media = MediaFileUpload(str(local_path), mimetype=mime, resumable=False)

        existing_id = self._find_file(local_path.name, folder_id)
        if existing_id:
            file = (
                service.files()
                .update(fileId=existing_id, media_body=media)
                .execute()
            )
            logger.info("Drive 파일 업데이트: %s", local_path.name)
        else:
            metadata = {"name": local_path.name, "parents": [folder_id]}
            file = (
                service.files()
                .create(body=metadata, media_body=media, fields="id")
                .execute()
            )
            logger.info("Drive 파일 업로드: %s", local_path.name)

        return file["id"]

    def sync_keyword_folder(self, keyword: str, local_folder: Path) -> None:
        """
        로컬 키워드 폴더의 파일들을 Drive에 동기화.

        results.json, scam_urls.txt, report.json 중 존재하는 파일만 업로드.
        """
        try:
            drive_folder_id = self.get_or_create_folder(keyword, self.root_folder_id)
            for filename in ("results.json", "scam_urls.txt", "report.json"):
                file_path = local_folder / filename
                if file_path.exists():
                    self.upload_file(file_path, drive_folder_id)
            logger.info("'%s' Google Drive 동기화 완료", keyword)
        except Exception as exc:
            logger.error("Google Drive 동기화 실패 ('%s'): %s", keyword, exc)
