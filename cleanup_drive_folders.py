"""
Google Drive 폴더 중복 정리 스크립트.

중복 기준:
  - 숫자 접미사: '260417 골드리치 2' == '260417 골드리치'
  - 띄어쓰기:   '260417 구본진 애널리스트' == '260417 구본진애널리스트'
  - 조합:       위 두 가지 동시 적용

사용법:
  python cleanup_drive_folders.py --date 260417          # 해당 날짜 폴더 미리보기
  python cleanup_drive_folders.py --date 260417 --delete # 실제 삭제
  python cleanup_drive_folders.py --delete               # 전체 날짜 정리
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict

from google_drive_manager import GoogleDriveManager, _normalize, _is_duplicate_name
from config import (
    GOOGLE_DRIVE_CREDENTIALS_FILE,
    GOOGLE_DRIVE_ROOT_FOLDER_ID,
    GOOGLE_DRIVE_TOKEN_FILE,
)

_UNSAFE = re.compile(r'[\\/:*?"<>|]')


def _normalize_folder(name: str) -> str:
    """날짜 접두사 유지하면서 뒷부분만 정규화."""
    # "260417 골드리치 2" → prefix="260417", body="골드리치 2"
    parts = name.split(" ", 1)
    if len(parts) == 2 and parts[0].isdigit():
        prefix, body = parts
        return prefix + "_" + _normalize(body)
    return _normalize(name)


def find_duplicates(folders: list[dict]) -> list[list[dict]]:
    """
    _is_duplicate_name 기준으로 중복 그룹 탐지.
    그룹 내에서 이름이 짧은 것(원본)을 첫 번째로 정렬.
    """
    visited = set()
    groups = []

    for i, f in enumerate(folders):
        if f["id"] in visited:
            continue
        group = [f]
        visited.add(f["id"])
        for g in folders[i + 1:]:
            if g["id"] not in visited and _is_duplicate_name(f["name"], g["name"]):
                group.append(g)
                visited.add(g["id"])
        if len(group) >= 2:
            group.sort(key=lambda x: len(x["name"]))  # 짧은 이름(원본) 우선
            groups.append(group)

    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Drive 중복 폴더 정리")
    parser.add_argument("--date", help="정리할 날짜 접두사 (예: 260417). 생략시 전체")
    parser.add_argument("--delete", action="store_true", help="실제 삭제 수행 (없으면 미리보기만)")
    args = parser.parse_args()

    dm = GoogleDriveManager(
        credentials_file=GOOGLE_DRIVE_CREDENTIALS_FILE,
        token_file=GOOGLE_DRIVE_TOKEN_FILE,
        root_folder_id=GOOGLE_DRIVE_ROOT_FOLDER_ID or None,
    )

    print("Drive 폴더 목록 가져오는 중...")
    all_folders = dm._list_root_folders()

    # 날짜 필터
    if args.date:
        folders = [f for f in all_folders if f["name"].startswith(args.date)]
        print(f"'{args.date}' 접두사 폴더: {len(folders)}개")
    else:
        folders = all_folders
        print(f"전체 폴더: {len(folders)}개")

    duplicates = find_duplicates(folders)

    if not duplicates:
        print("중복 폴더 없음. 정리 완료.")
        return

    print(f"\n중복 그룹 {len(duplicates)}개 발견:\n")
    to_delete: list[dict] = []

    for items in duplicates:
        original = items[0]
        dups = items[1:]
        print(f"  ✅ 유지: {original['name']}")
        for d in dups:
            print(f"  🗑  삭제: {d['name']}")
            to_delete.append(d)
        print()

    print(f"총 {len(to_delete)}개 폴더 삭제 예정")

    if not args.delete:
        print("\n※ 실제 삭제하려면 --delete 옵션을 추가하세요.")
        return

    confirm = input("\n정말 삭제하시겠습니까? (yes 입력): ").strip()
    if confirm != "yes":
        print("취소됨.")
        return

    service = dm._get_service()
    for folder in to_delete:
        service.files().delete(fileId=folder["id"]).execute()
        print(f"삭제 완료: {folder['name']}")

    print(f"\n정리 완료: {len(to_delete)}개 폴더 삭제됨.")


if __name__ == "__main__":
    main()
