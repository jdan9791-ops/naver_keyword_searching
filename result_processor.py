"""
검색 결과 후처리 모듈.

주요 기능
─────────
- 법률사무소 관련 항목 제거
- 사기사이트/거래소 URL 우선 정렬
- URL 없는 항목 표시 및 분리
- HTML 태그 제거 (Naver API 응답에 <b> 태그 포함)
"""
from __future__ import annotations

import re
import logging
from typing import Any

from config import EXCLUDE_KEYWORDS, SCAM_PRIORITY_KEYWORDS

logger = logging.getLogger(__name__)

_HTML_TAG = re.compile(r"<[^>]+>")


# ── 텍스트 정제 ────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Naver API 응답의 HTML 태그 제거."""
    return _HTML_TAG.sub("", text).strip()


def clean_item(item: dict[str, Any]) -> dict[str, Any]:
    """title, description 등 텍스트 필드에서 HTML 제거."""
    cleaned = dict(item)
    for field in ("title", "description", "bloggername", "postdate"):
        if field in cleaned:
            cleaned[field] = strip_html(str(cleaned[field]))
    return cleaned


# ── 필터링 ─────────────────────────────────────────────────────────────────────

def _contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def is_law_firm_result(item: dict[str, Any]) -> bool:
    """법률사무소 관련 항목이면 True."""
    combined = " ".join([
        item.get("title", ""),
        item.get("description", ""),
    ])
    return _contains_any(combined, EXCLUDE_KEYWORDS)


def is_scam_related(item: dict[str, Any]) -> bool:
    """사기/피해 관련 항목이면 True (우선순위 상향용)."""
    combined = " ".join([
        item.get("title", ""),
        item.get("description", ""),
    ])
    return _contains_any(combined, SCAM_PRIORITY_KEYWORDS)


# ── 정렬 ───────────────────────────────────────────────────────────────────────

def sort_key(item: dict[str, Any]) -> tuple[int, int]:
    """
    정렬 기준 (낮을수록 앞):
    1. URL 있음 → 0, 없음 → 1
    2. 사기 관련 → 0, 아님 → 1
    """
    has_url = 0 if item.get("link", "").strip() else 1
    is_scam = 0 if is_scam_related(item) else 1
    return (has_url, is_scam)


# ── 통합 처리 ─────────────────────────────────────────────────────────────────

class ResultProcessor:
    """
    Naver 검색 결과 리스트를 받아 정제·필터·정렬합니다.

    Parameters
    ----------
    remove_law_firms : bool
        법률사무소 관련 결과 제거 여부 (기본 True)
    """

    def __init__(self, remove_law_firms: bool = True) -> None:
        self.remove_law_firms = remove_law_firms

    def process(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        1. HTML 태그 제거
        2. 법률사무소 항목 제거 (옵션)
        3. 사기 관련 / URL 보유 항목 우선 정렬
        """
        # HTML 정제
        items = [clean_item(item) for item in items]

        # 법률사무소 필터
        if self.remove_law_firms:
            before = len(items)
            items = [item for item in items if not is_law_firm_result(item)]
            removed = before - len(items)
            if removed:
                logger.info("법률사무소 관련 항목 %d건 제거", removed)

        # URL 없는 항목 경고 로그
        no_url = [item for item in items if not item.get("link", "").strip()]
        if no_url:
            logger.warning("URL 없는 항목 %d건 포함됨", len(no_url))

        # 정렬: URL 있고 사기 관련인 항목 최우선
        items.sort(key=sort_key)

        return items

    def get_scam_urls(self, items: list[dict[str, Any]]) -> list[str]:
        """사기 관련 항목의 URL 목록만 추출."""
        return [
            item["link"]
            for item in items
            if item.get("link", "").strip() and is_scam_related(item)
        ]

    def report(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """처리 결과 요약 통계."""
        total = len(items)
        with_url = sum(1 for i in items if i.get("link", "").strip())
        scam_related = sum(1 for i in items if is_scam_related(i))
        return {
            "total": total,
            "with_url": with_url,
            "without_url": total - with_url,
            "scam_related": scam_related,
            "url_coverage_pct": round(with_url / total * 100, 1) if total else 0,
        }
