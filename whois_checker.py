"""
도메인 등록일(생성일) 조회 모듈.

- .kr / .한국 도메인 → KISA Open API (data.go.kr)
- 그 외 (.org .com .net 등) → RDAP API (rdap.org, 무료/인증 불필요)
- 배치 병렬 처리 지원
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests

from config import KISA_API_KEY, URL_CHECK_CONCURRENCY, URL_TIMEOUT

logger = logging.getLogger(__name__)

_KR_TLDS = {".kr", ".한국"}
_RDAP_URL = "https://rdap.org/domain/{domain}"
_KISA_URL = "https://apis.data.go.kr/B551505/whois/domain_name"


# ── 도메인 추출 ────────────────────────────────────────────────────────────────

def extract_domain(url: str) -> str:
    """URL에서 도메인(호스트)만 추출. 실패 시 원본 반환."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return urlparse(url).netloc or url


def _is_kr_domain(domain: str) -> bool:
    """한국 도메인(.kr, .한국) 여부 확인."""
    domain = domain.lower()
    return any(domain.endswith(tld) for tld in _KR_TLDS)


# ── KISA API (.kr / .한국) ────────────────────────────────────────────────────

def _query_kisa(domain: str, timeout: int = URL_TIMEOUT) -> Optional[str]:
    """
    KISA Open API로 .kr 도메인 등록일 조회.
    성공 시 'YYYY. MM. DD.' 형식 문자열 반환, 실패 시 None.
    """
    try:
        resp = requests.get(
            _KISA_URL,
            params={"serviceKey": KISA_API_KEY, "query": domain, "answer": "json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        result_code = data.get("response", {}).get("result", {}).get("result_code")
        if result_code != "10000":
            logger.warning("KISA API 오류 [%s]: %s", domain, result_code)
            return None
        whois = data.get("response", {}).get("whois", {})
        # krdomain 또는 krhanguldomain 키 처리
        domain_info = whois.get("krdomain") or whois.get("krhanguldomain") or {}
        return domain_info.get("regDate") or None
    except Exception as exc:
        logger.warning("KISA 조회 실패 [%s]: %s", domain, exc)
        return None


# ── RDAP API (해외 도메인) ────────────────────────────────────────────────────

def _query_rdap(domain: str, timeout: int = URL_TIMEOUT) -> Optional[str]:
    """
    RDAP API로 해외 도메인 등록일 조회.
    성공 시 ISO 8601 형식 문자열 반환, 실패 시 None.
    """
    try:
        resp = requests.get(
            _RDAP_URL.format(domain=domain),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                return event.get("eventDate")
        return None
    except Exception as exc:
        logger.warning("RDAP 조회 실패 [%s]: %s", domain, exc)
        return None


# ── 단건 조회 ─────────────────────────────────────────────────────────────────

@dataclass
class WhoisResult:
    domain: str
    reg_date: Optional[str]    # 등록(생성)일
    source: str                # "kisa" | "rdap" | "error"
    error: Optional[str] = None

    @property
    def reg_date_short(self) -> str:
        """날짜만 간결하게 반환 (YYYY-MM-DD 또는 원본)."""
        if not self.reg_date:
            return "조회 실패"
        # ISO 형식: 2004-01-28T00:00:00Z → 2004-01-28
        match = re.search(r"\d{4}-\d{2}-\d{2}", self.reg_date)
        if match:
            return match.group()
        # KISA 형식: 2007. 02. 28. → 2007-02-28
        match = re.search(r"(\d{4})\.\s*(\d{2})\.\s*(\d{2})", self.reg_date)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return self.reg_date


def check_whois(url: str, timeout: int = URL_TIMEOUT) -> WhoisResult:
    """URL(또는 도메인) 하나의 도메인 등록일 조회."""
    domain = extract_domain(url)
    if not domain:
        return WhoisResult(domain=url, reg_date=None, source="error", error="도메인 추출 실패")

    if _is_kr_domain(domain):
        if not KISA_API_KEY:
            return WhoisResult(domain=domain, reg_date=None, source="error",
                               error="KISA_API_KEY 환경변수 미설정")
        reg_date = _query_kisa(domain, timeout)
        source = "kisa"
    else:
        reg_date = _query_rdap(domain, timeout)
        source = "rdap"

    return WhoisResult(domain=domain, reg_date=reg_date, source=source)


# ── 배치 조회 ─────────────────────────────────────────────────────────────────

def check_whois_batch(
    urls: list[str],
    concurrency: int = min(URL_CHECK_CONCURRENCY, 5),  # RDAP 과부하 방지
    timeout: int = URL_TIMEOUT,
) -> dict[str, WhoisResult]:
    """
    여러 URL을 병렬로 Whois 조회.

    Returns
    -------
    dict[url → WhoisResult]
    """
    results: dict[str, WhoisResult] = {}
    unique_urls = list(dict.fromkeys(u for u in urls if u))

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_url = {
            executor.submit(check_whois, url, timeout): url
            for url in unique_urls
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = WhoisResult(
                    domain=extract_domain(url), reg_date=None,
                    source="error", error=str(exc)
                )
            logger.debug("Whois [%s]: %s", url, results[url].reg_date_short)

    return results


def attach_whois_to_items(
    items: list[dict],
    url_field: str = "link",
    results: Optional[dict[str, WhoisResult]] = None,
) -> list[dict]:
    """
    items 각각에 'domain_created' 필드를 추가해 반환.
    results가 None이면 실시간 조회.
    """
    if results is None:
        urls = [item.get(url_field, "") for item in items if item.get(url_field, "").strip()]
        results = check_whois_batch(urls)

    updated = []
    for item in items:
        item = dict(item)
        url = item.get(url_field, "").strip()
        if url and url in results:
            item["domain_created"] = results[url].reg_date_short
        else:
            item["domain_created"] = ""
        updated.append(item)

    return updated
