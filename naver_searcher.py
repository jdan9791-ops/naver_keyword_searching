"""
Naver Open API를 통해 웹/뉴스/블로그 검색을 수행합니다.
환경변수 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 필요.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from config import (
    NAVER_BLOG_URL,
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_NEWS_URL,
    NAVER_SEARCH_URL,
    SEARCH_DISPLAY,
    SEARCH_START,
)

logger = logging.getLogger(__name__)


class NaverSearchError(Exception):
    pass


class NaverSearcher:
    """Naver Open API 검색 클라이언트."""

    def __init__(
        self,
        client_id: str = NAVER_CLIENT_ID,
        client_secret: str = NAVER_CLIENT_SECRET,
        retry: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        if not client_id or not client_secret:
            raise NaverSearchError(
                "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수를 설정해 주세요."
            )
        self.headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        self.retry = retry
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _get(self, url: str, params: dict) -> dict:
        """재시도 로직 포함 GET 요청."""
        for attempt in range(1, self.retry + 1):
            try:
                resp = self.session.get(url, params=params, timeout=10)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.retry:
                    raise NaverSearchError(f"Naver API 오류: {exc}") from exc
                logger.warning("재시도 %d/%d: %s", attempt, self.retry, exc)
                time.sleep(self.retry_delay * attempt)
        return {}

    def _search(self, base_url: str, query: str, display: int, start: int) -> list[dict]:
        """공통 검색 로직. 결과 리스트를 반환."""
        params = {"query": query, "display": display, "start": start}
        data = self._get(base_url, params)
        items = data.get("items", [])
        logger.info("'%s' 검색 결과: %d건", query, len(items))
        return items

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def search_web(
        self,
        query: str,
        display: int = SEARCH_DISPLAY,
        start: int = SEARCH_START,
    ) -> list[dict]:
        """Naver 웹 검색."""
        return self._search(NAVER_SEARCH_URL, query, display, start)

    def search_news(
        self,
        query: str,
        display: int = SEARCH_DISPLAY,
        start: int = SEARCH_START,
    ) -> list[dict]:
        """Naver 뉴스 검색."""
        return self._search(NAVER_NEWS_URL, query, display, start)

    def search_blog(
        self,
        query: str,
        display: int = SEARCH_DISPLAY,
        start: int = SEARCH_START,
    ) -> list[dict]:
        """Naver 블로그 검색."""
        return self._search(NAVER_BLOG_URL, query, display, start)

    def search_all(
        self,
        query: str,
        display: int = SEARCH_DISPLAY,
    ) -> list[dict]:
        """웹 + 뉴스 + 블로그 통합 검색. 중복 URL 자동 제거."""
        results: list[dict] = []
        seen_links: set[str] = set()

        for search_fn in (self.search_web, self.search_news, self.search_blog):
            try:
                items = search_fn(query, display=display)
                for item in items:
                    link = item.get("link") or item.get("bloggerlink", "")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        item["_source"] = search_fn.__name__.replace("search_", "")
                        results.append(item)
            except NaverSearchError as exc:
                logger.warning("검색 오류 (%s): %s", search_fn.__name__, exc)

        return results
