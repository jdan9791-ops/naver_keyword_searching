"""
Google Drive 폴더 중복 정리 스크립트.

날짜를 가로질러 동일 회사 폴더 중복 감지.
예) 20260419/260419 골드문퀵머니
    20260420/260420 골드문 퀵머니 GoldMoon 해외송금  ← 중복 → 삭제

사용법:
  python cleanup_drive_folders.py               # 전체 날짜 중복 미리보기
  python cleanup_drive_folders.py --delete      # 전체 날짜 중복 삭제 (오래된 것 유지)
  python cleanup_drive_folders.py --target 260420          # 20일 폴더 기준 미리보기
  python cleanup_drive_folders.py --target 260420 --delete # 20일 중복만 삭제
"""
from __future__ import annotations

import argparse
import sys

from google_drive_manager import GoogleDriveManager, _is_duplicate_name
from config import (
    GOOGLE_DRIVE_CREDENTIALS_FILE,
    GOOGLE_DRIVE_ROOT_FOLDER_ID,
    GOOGLE_DRIVE_TOKEN_FILE,
)


def collect_all_company_folders(service, root_id: str) -> list[dict]:
    """
    모든 날짜 하위 폴더 안의 회사 폴더를 수집.
    각 항목: {id, name, date_folder}
    """
    def list_folders(parent_id: str) -> list[dict]:
        q = (f"'{parent_id}' in parents and "
             f"mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        res = service.files().list(q=q, fields="files(id, name)", pageSize=1000).execute()
        return res.get("files", [])

    root_folders = list_folders(root_id)
    company_folders = []

    for folder in sorted(root_folders, key=lambda x: x["name"]):
        name = folder["name"]
        # 숫자로만 된 폴더 = 날짜 폴더 (예: 20260419)
        if name.isdigit():
            for company in list_folders(folder["id"]):
                company_folders.append({**company, "date_folder": name})
        elif name != "0 source":
            # 날짜 폴더 없이 root에 바로 있는 회사 폴더
            company_folders.append({**folder, "date_folder": ""})

    return company_folders


def find_cross_date_duplicates(
    all_folders: list[dict],
    target_date: str | None = None,
) -> list[list[dict]]:
    """
    날짜를 가로질러 중복 그룹 탐지.
    그룹 내 정렬: 날짜 폴더 이름 오름차순 (오래된 것 앞).
    target_date: 이 날짜 폴더의 항목이 포함된 그룹만 반환.
    """
    visited = set()
    groups = []

    for i, a in enumerate(all_folders):
        if a["id"] in visited:
            continue
        group = [a]
        visited.add(a["id"])
        for b in all_folders[i + 1:]:
            if b["id"] not in visited and _is_duplicate_name(a["name"], b["name"]):
                group.append(b)
                visited.add(b["id"])
        if len(group) >= 2:
            # 오래된 날짜 폴더 순으로 정렬 → 첫 번째가 원본
            group.sort(key=lambda x: (x["date_folder"], x["name"]))
            if target_date is None or any(target_date in f["date_folder"] for f in group):
                groups.append(group)

    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Drive 날짜 간 중복 폴더 정리")
    parser.add_argument("--target", help="삭제 대상 날짜 (예: 260420). 생략시 전체")
    parser.add_argument("--delete", action="store_true", help="실제 삭제 수행")
    args = parser.parse_args()

    dm = GoogleDriveManager(
        credentials_file=GOOGLE_DRIVE_CREDENTIALS_FILE,
        token_file=GOOGLE_DRIVE_TOKEN_FILE,
        root_folder_id=GOOGLE_DRIVE_ROOT_FOLDER_ID or None,
    )

    print("Drive 폴더 목록 가져오는 중...")
    service = dm._get_service()
    all_folders = collect_all_company_folders(service, GOOGLE_DRIVE_ROOT_FOLDER_ID)
    print(f"전체 회사 폴더: {len(all_folders)}개\n")

    duplicates = find_cross_date_duplicates(all_folders, target_date=args.target)

    if not duplicates:
        print("중복 폴더 없음.")
        return

    print(f"중복 그룹 {len(duplicates)}개 발견:\n")
    to_delete: list[dict] = []

    for group in duplicates:
        original = group[0]
        dups = [f for f in group[1:] if args.target is None or args.target in f["date_folder"]]
        if not dups:
            continue
        print(f"  ✅ 유지: [{original['date_folder']}] {original['name']}")
        for d in dups:
            print(f"  🗑  삭제: [{d['date_folder']}] {d['name']}")
            to_delete.append(d)
        print()

    if not to_delete:
        print("삭제 대상 없음.")
        return

    print(f"총 {len(to_delete)}개 폴더 삭제 예정")

    if not args.delete:
        print("\n※ 실제 삭제하려면 --delete 옵션을 추가하세요.")
        return

    confirm = input("\n정말 삭제하시겠습니까? (yes 입력): ").strip()
    if confirm != "yes":
        print("취소됨.")
        return

    for folder in to_delete:
        service.files().delete(fileId=folder["id"]).execute()
        print(f"삭제 완료: [{folder['date_folder']}] {folder['name']}")

    print(f"\n정리 완료: {len(to_delete)}개 폴더 삭제됨.")


if __name__ == "__main__":
    main()
