"""
URL 접근 가능 여부를 확인하는 모듈.

- 단건 / 배치 지원
- concurrent.futures를 이용한 병렬 체크
- 리다이렉트 추적, 타임아웃, HTTP 상태 코드 보고
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests
from requests import Response

from config import MAX_REDIRECTS, URL_CHECK_CONCURRENCY, URL_TIMEOUT

logger = logging.getLogger(__name__)

# 브라우저처럼 보이는 User-Agent (일부 사이트 차단 우회)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0 Safari/537.36"
)


@dataclass
class URLStatus:
    url: str
    accessible: bool
    status_code: Optional[int] = None
    final_url: Optional[str] = None   # 리다이렉트 최종 URL
    error: Optional[str] = None
    is_scam_domain: bool = False       # 알려진 사기 도메인 여부 (미래 확장용)

    @property
    def summary(self) -> str:
        if self.accessible:
            redirect = f" → {self.final_url}" if self.final_url and self.final_url != self.url else ""
            return f"✅ {self.status_code}{redirect}"
        return f"❌ {self.error or self.status_code}"


# ── 유효성 사전 검사 ───────────────────────────────────────────────────────────

def _is_valid_url(url: str) -> bool:
    """URL 기본 형식 검사."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


# ── 단건 체크 ─────────────────────────────────────────────────────────────────

def check_url(url: str, timeout: int = URL_TIMEOUT) -> URLStatus:
    """URL 하나의 접근 가능 여부 확인."""
    if not url or not url.strip():
        return URLStatus(url=url, accessible=False, error="URL 없음")

    url = url.strip()

    if not _is_valid_url(url):
        return URLStatus(url=url, accessible=False, error="잘못된 URL 형식")

    try:
        resp: Response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": _UA},
            allow_redirects=True,
            max_redirects=MAX_REDIRECTS,
        )
        final_url = resp.url if resp.url != url else None
        accessible = resp.status_code < 400
        return URLStatus(
            url=url,
            accessible=accessible,
            status_code=resp.status_code,
            final_url=final_url,
            error=None if accessible else f"HTTP {resp.status_code}",
        )
    except requests.exceptions.Timeout:
        return URLStatus(url=url, accessible=False, error="타임아웃")
    except requests.exceptions.TooManyRedirects:
        return URLStatus(url=url, accessible=False, error="리다이렉트 과다")
    except requests.exceptions.ConnectionError:
        return URLStatus(url=url, accessible=False, error="연결 실패")
    except requests.exceptions.RequestException as exc:
        return URLStatus(url=url, accessible=False, error=str(exc))


# ── 배치 체크 ─────────────────────────────────────────────────────────────────

def check_urls_batch(
    urls: list[str],
    concurrency: int = URL_CHECK_CONCURRENCY,
    timeout: int = URL_TIMEOUT,
) -> dict[str, URLStatus]:
    """
    여러 URL을 병렬로 체크.

    Returns
    -------
    dict[url → URLStatus]
    """
    results: dict[str, URLStatus] = {}
    unique_urls = list(dict.fromkeys(u for u in urls if u))  # 순서 유지 중복 제거

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_url = {
            executor.submit(check_url, url, timeout): url
            for url in unique_urls
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = URLStatus(url=url, accessible=False, error=str(exc))
            logger.debug("URL 체크: %s → %s", url, results[url].summary)

    return results


# ── 결과 분류 헬퍼 ────────────────────────────────────────────────────────────

def split_by_accessibility(
    statuses: dict[str, URLStatus],
) -> tuple[list[URLStatus], list[URLStatus]]:
    """접근 가능 / 불가 목록으로 분리."""
    accessible = [s for s in statuses.values() if s.accessible]
    inaccessible = [s for s in statuses.values() if not s.accessible]
    return accessible, inaccessible


def filter_accessible_items(
    items: list[dict],
    url_field: str = "link",
    statuses: Optional[dict[str, URLStatus]] = None,
) -> list[dict]:
    """
    items 리스트에서 URL이 접근 가능한 항목만 반환.
    URL이 없는 항목은 그대로 포함 (URL 없음 != 접근 불가).
    statuses가 None이면 실시간으로 체크.
    """
    if statuses is None:
        urls = [item.get(url_field, "") for item in items]
        statuses = check_urls_batch([u for u in urls if u])

    result = []
    for item in items:
        url = item.get(url_field, "").strip()
        if not url:
            # URL 없는 항목: 포함하되 표시
            item = dict(item)
            item["_url_status"] = "URL 없음"
            result.append(item)
        elif statuses.get(url, URLStatus(url=url, accessible=False)).accessible:
            item = dict(item)
            item["_url_status"] = statuses[url].summary
            result.append(item)
        else:
            status = statuses.get(url)
            logger.info("접근 불가 URL 제외: %s (%s)", url, status.error if status else "")

    return result
