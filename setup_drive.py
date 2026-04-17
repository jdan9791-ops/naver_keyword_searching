"""
Google Drive 연동 최초 설정 스크립트.

실행하면:
  1. credentials.json으로 브라우저 OAuth 인증 → token.json 생성
  2. keyword_filter_DB 폴더 ID 자동 탐색 또는 입력
  3. .env 파일에 설정 저장 (이후 자동화에서 자동 로드)

사용법:
  python setup_drive.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"


def write_env(folder_id: str) -> None:
    lines = [
        "GOOGLE_DRIVE_ENABLED=true",
        f"GOOGLE_DRIVE_ROOT_FOLDER_ID={folder_id}",
        f"GOOGLE_DRIVE_CREDENTIALS_FILE={CREDENTIALS_FILE}",
        f"GOOGLE_DRIVE_TOKEN_FILE={Path(__file__).parent / 'token.json'}",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n✅ 설정 저장 완료: {ENV_FILE}")


def find_keyword_filter_db(dm) -> str | None:
    """Drive 최상위에서 'keyword_filter_DB' 폴더 검색."""
    service = dm._get_service()
    result = service.files().list(
        q="name = 'keyword_filter_DB' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name)",
    ).execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def main() -> None:
    if not CREDENTIALS_FILE.exists():
        print("❌ credentials.json 파일이 없습니다.")
        print(f"   Google Cloud Console에서 다운로드 후 {CREDENTIALS_FILE} 에 저장하세요.")
        sys.exit(1)

    print("=" * 50)
    print("Google Drive 연동 설정")
    print("=" * 50)

    # Google Drive 인증 (브라우저 열림)
    print("\n브라우저에서 Google 계정 인증을 진행합니다...")
    sys.path.insert(0, str(Path(__file__).parent))
    from google_drive_manager import GoogleDriveManager

    dm = GoogleDriveManager(
        credentials_file=CREDENTIALS_FILE,
        token_file=Path(__file__).parent / "token.json",
        root_folder_id=None,
    )
    dm._get_service()
    print("✅ 인증 완료 (token.json 저장됨)")

    # keyword_filter_DB 폴더 자동 탐색
    print("\n'keyword_filter_DB' 폴더 탐색 중...")
    folder_id = find_keyword_filter_db(dm)

    if folder_id:
        print(f"✅ 폴더 발견 (ID: {folder_id})")
    else:
        print("폴더를 자동으로 찾지 못했습니다.")
        print("Google Drive에서 keyword_filter_DB 폴더를 열고")
        print("URL 끝의 ID를 복사해 붙여넣으세요.")
        print("예) https://drive.google.com/drive/folders/[여기가ID]")
        folder_id = input("\nFolder ID: ").strip()
        if not folder_id:
            print("❌ 입력 없음. 종료.")
            sys.exit(1)

    write_env(folder_id)

    print("\n설정 완료! 이제 자동화 실행 시 Google Drive 연동이 활성화됩니다.")
    print("테스트: python main.py search --keywords '테스트키워드'")


if __name__ == "__main__":
    main()
