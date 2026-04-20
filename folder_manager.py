"""
검색 결과를 키워드별 폴더에 저장·불러오기·중복 정리하는 모듈.

폴더 구조
─────────
results/
  └── {keyword}/
        ├── results.json      # 처리된 검색 결과 전체
        ├── scam_urls.txt     # 사기사이트/거래소 URL 목록
        └── report.json       # 요약 통계
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import datetime

from config import (
    GOOGLE_DRIVE_CREDENTIALS_FILE,
    GOOGLE_DRIVE_ENABLED,
    GOOGLE_DRIVE_ROOT_FOLDER_ID,
    GOOGLE_DRIVE_TOKEN_FILE,
    KEYWORD_HISTORY_FILE,
    OUTPUT_DIR,
    SIMILARITY_THRESHOLD,
)
from deduplicator import KoreanDeduplicator, deduplicate_strings

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')
_TRAILING_NUMBER = re.compile(r'\s+\d+$')
_DATE_PREFIX = re.compile(r'^\d{6}\s*')


def _safe_dirname(keyword: str) -> str:
    """파일시스템에 안전한 폴더명으로 변환."""
    return _UNSAFE_CHARS.sub("_", keyword).strip()


def _normalize_keyword(name: str) -> str:
    """중복 비교용 정규화: 날짜 접두사 제거 + 숫자 접미사 제거 + 공백 제거 + 소문자."""
    name = _DATE_PREFIX.sub("", name)
    name = _TRAILING_NUMBER.sub("", name).strip()
    name = re.sub(r'\s+', '', name)
    return name.lower()


def _is_duplicate_keyword(a: str, b: str) -> bool:
    na, nb = _normalize_keyword(a), _normalize_keyword(b)
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 4 and longer.startswith(shorter)


class FolderManager:
    """
    키워드별 결과 폴더를 관리합니다.

    Parameters
    ----------
    base_dir : str | Path
        결과 저장 루트 경로 (기본: config.OUTPUT_DIR)
    """

    def __init__(self, base_dir: str | Path = OUTPUT_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._history_file = Path(KEYWORD_HISTORY_FILE)
        self._drive: Any = None
        if GOOGLE_DRIVE_ENABLED:
            self._init_drive()

    # ── 키워드 이력 관리 ──────────────────────────────────────────────────────

    def _load_history(self) -> list[dict]:
        if not self._history_file.exists():
            return []
        with self._history_file.open(encoding="utf-8") as f:
            return json.load(f)

    def _save_history(self, history: list[dict]) -> None:
        with self._history_file.open("w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def _add_to_history(self, keyword: str) -> None:
        history = self._load_history()
        norm = _normalize_keyword(keyword)
        if not any(e["normalized"] == norm for e in history):
            history.append({
                "keyword": keyword,
                "normalized": norm,
                "date": datetime.date.today().isoformat(),
            })
            self._save_history(history)
            logger.info("이력 추가: '%s'", keyword)

    def _init_drive(self) -> None:
        from google_drive_manager import GoogleDriveManager
        self._drive = GoogleDriveManager(
            credentials_file=GOOGLE_DRIVE_CREDENTIALS_FILE,
            token_file=GOOGLE_DRIVE_TOKEN_FILE,
            root_folder_id=GOOGLE_DRIVE_ROOT_FOLDER_ID or None,
        )
        logger.info("Google Drive 동기화 활성화")

    # ── 중복 키워드 체크 ──────────────────────────────────────────────────────

    def is_duplicate_keyword(self, keyword: str) -> str | None:
        """
        이력 파일 + 로컬 폴더 기준으로 중복 여부 확인.
        중복이면 기존 키워드명 반환, 없으면 None.
        """
        # 1. 누적 이력 파일 확인 (results 폴더 삭제돼도 유지)
        for entry in self._load_history():
            if entry["normalized"] == _normalize_keyword(keyword):
                if entry["keyword"] != keyword:
                    return entry["keyword"]
            elif _is_duplicate_keyword(keyword, entry["keyword"]):
                return entry["keyword"]

        # 2. 로컬 폴더 확인 (이력에 없는 경우 보완)
        for existing in self.list_keywords():
            if existing == _safe_dirname(keyword):
                continue
            if _is_duplicate_keyword(keyword, existing):
                return existing

        return None

    # ── 경로 헬퍼 ─────────────────────────────────────────────────────────────

    def keyword_dir(self, keyword: str) -> Path:
        folder = self.base_dir / _safe_dirname(keyword)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # ── 저장 ──────────────────────────────────────────────────────────────────

    def save_results(
        self,
        keyword: str,
        items: list[dict[str, Any]],
        scam_urls: list[str] | None = None,
        report: dict[str, Any] | None = None,
    ) -> Path:
        """
        results.json, scam_urls.txt, report.json 저장.

        Returns
        -------
        Path
            저장된 키워드 폴더 경로
        """
        folder = self.keyword_dir(keyword)

        # results.json
        results_path = folder / "results.json"
        with results_path.open("w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        logger.info("저장: %s (%d건)", results_path, len(items))

        # scam_urls.txt
        if scam_urls is not None:
            urls_path = folder / "scam_urls.txt"
            with urls_path.open("w", encoding="utf-8") as f:
                f.write("\n".join(scam_urls))
            logger.info("사기 URL %d개 저장: %s", len(scam_urls), urls_path)

        # report.json
        if report is not None:
            report_path = folder / "report.json"
            with report_path.open("w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        # 키워드 이력 누적 저장
        self._add_to_history(keyword)

        if self._drive is not None:
            self._drive.sync_keyword_folder(keyword, folder)

        return folder

    # ── 불러오기 ──────────────────────────────────────────────────────────────

    def load_results(self, keyword: str) -> list[dict[str, Any]]:
        """저장된 results.json 불러오기. 없으면 빈 리스트 반환."""
        path = self.keyword_dir(keyword) / "results.json"
        if not path.exists():
            logger.warning("결과 파일 없음: %s", path)
            return []
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def load_scam_urls(self, keyword: str) -> list[str]:
        """저장된 scam_urls.txt 불러오기."""
        path = self.keyword_dir(keyword) / "scam_urls.txt"
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    # ── 폴더 내 중복 정리 ─────────────────────────────────────────────────────

    def deduplicate_folder(
        self,
        keyword: str,
        key_field: str = "title",
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> dict[str, int]:
        """
        기존 results.json을 읽어 중복 제거 후 덮어씁니다.

        Returns
        -------
        dict
            {"before": N, "after": M, "removed": K}
        """
        items = self.load_results(keyword)
        if not items:
            return {"before": 0, "after": 0, "removed": 0}

        deduper = KoreanDeduplicator(key_field=key_field, threshold=threshold)
        deduped = deduper.deduplicate(items)

        before = len(items)
        after = len(deduped)

        self.save_results(keyword, deduped)
        logger.info(
            "'%s' 중복 제거: %d → %d건 (-%d)", keyword, before, after, before - after
        )
        return {"before": before, "after": after, "removed": before - after}

    # ── 폴더명(키워드) 수준 중복 정리 ────────────────────────────────────────

    def deduplicate_keyword_folders(
        self,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> list[tuple[str, str]]:
        """
        폴더명이 서로 유사한 경우(띄어쓰기 차이 등)를 찾아 보고.
        실제 병합은 수행하지 않음 (안전 우선). 결과를 반환해 사용자가 확인.

        Returns
        -------
        list[tuple[str, str]]
            유사 폴더명 쌍 리스트: [(folder_a, folder_b), ...]
        """
        folders = [p.name for p in self.base_dir.iterdir() if p.is_dir()]
        deduped = deduplicate_strings(folders, threshold)

        # 원본 목록 vs 중복제거 목록 비교로 유사 쌍 추출
        from deduplicator import text_similarity

        pairs: list[tuple[str, str]] = []
        seen: set[frozenset] = set()
        for i, a in enumerate(folders):
            for b in folders[i + 1:]:
                if frozenset({a, b}) not in seen:
                    if text_similarity(a, b) >= threshold:
                        pairs.append((a, b))
                        seen.add(frozenset({a, b}))

        if pairs:
            logger.warning("유사 폴더명 %d쌍 발견:", len(pairs))
            for a, b in pairs:
                logger.warning("  '%s' ≈ '%s'", a, b)

        return pairs

    # ── 전체 현황 ─────────────────────────────────────────────────────────────

    def list_keywords(self) -> list[str]:
        """저장된 모든 키워드(폴더명) 목록."""
        return [p.name for p in sorted(self.base_dir.iterdir()) if p.is_dir()]

    def summary(self) -> list[dict[str, Any]]:
        """각 키워드별 저장 현황 요약."""
        summaries = []
        for keyword in self.list_keywords():
            items = self.load_results(keyword)
            scam_urls = self.load_scam_urls(keyword)
            with_url = sum(1 for i in items if i.get("link", "").strip())
            summaries.append({
                "keyword": keyword,
                "total": len(items),
                "with_url": with_url,
                "without_url": len(items) - with_url,
                "scam_urls": len(scam_urls),
            })
        return summaries
