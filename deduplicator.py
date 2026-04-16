"""
한국어 텍스트 중복 제거 모듈.

처리 전략
─────────
1. 공백 제거 정규화: '도산 신탁 프로젝트' == '도산신탁프로젝트'
2. SequenceMatcher 유사도: '당신의 자산 거래 동반자' ≈ '당신의 자산 거래 파트너'
3. Jaccard(토큰) 유사도: 단어 집합 겹침 비율 보조 검사
4. URL 보존 우선: 중복 그룹 내 URL 있는 항목을 대표로 선택
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from config import SIMILARITY_THRESHOLD


# ── 정규화 ────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    공백 전부 제거 + 유니코드 NFC 정규화 + 소문자.
    '도산 신탁 프로젝트' → '도산신탁프로젝트'
    """
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def _tokenize(text: str) -> set[str]:
    """공백 기준 토큰 집합 반환."""
    return set(text.strip().split())


# ── 유사도 계산 ────────────────────────────────────────────────────────────────

def sequence_similarity(a: str, b: str) -> float:
    """정규화된 문자열의 SequenceMatcher 유사도 (0~1)."""
    na, nb = _normalize(a), _normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def jaccard_similarity(a: str, b: str) -> float:
    """단어 집합 기반 Jaccard 유사도 (0~1)."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def text_similarity(a: str, b: str) -> float:
    """
    최종 유사도: SequenceMatcher(0.6) + Jaccard(0.4) 가중 평균.
    완전한 공백 차이 케이스는 정규화 후 exact match로 먼저 처리됨.
    """
    if _normalize(a) == _normalize(b):
        return 1.0
    seq = sequence_similarity(a, b)
    jac = jaccard_similarity(a, b)
    return 0.6 * seq + 0.4 * jac


# ── 중복 그룹화 ────────────────────────────────────────────────────────────────

def _group_duplicates(
    texts: list[str],
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[list[int]]:
    """
    Union-Find를 이용해 유사도 threshold 이상인 항목을 같은 그룹으로 묶음.
    반환: 인덱스 그룹 리스트 (각 그룹의 첫 항목이 대표).
    """
    n = len(texts)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            if text_similarity(texts[i], texts[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    return list(groups.values())


# ── 공개 인터페이스 ────────────────────────────────────────────────────────────

class KoreanDeduplicator:
    """
    딕셔너리 리스트에서 한국어 텍스트 기반 중복 항목을 제거합니다.

    Parameters
    ----------
    key_field : str
        유사도 비교에 사용할 딕셔너리 필드명 (예: "title", "name")
    url_field : str
        URL이 저장된 필드명. 중복 그룹 내 URL 있는 항목을 우선 보존.
    threshold : float
        유사도 임계값 (0~1). 기본값: config.SIMILARITY_THRESHOLD
    """

    def __init__(
        self,
        key_field: str = "title",
        url_field: str = "link",
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> None:
        self.key_field = key_field
        self.url_field = url_field
        self.threshold = threshold

    def deduplicate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        중복 제거 후 대표 항목 리스트 반환.
        각 중복 그룹에서:
          - URL이 있는 항목이 있으면 → URL 있는 것 중 가장 앞 항목
          - 모두 URL 없으면 → 그룹의 첫 번째 항목
        """
        if not items:
            return []

        texts = [str(item.get(self.key_field, "")) for item in items]
        groups = _group_duplicates(texts, self.threshold)

        result: list[dict[str, Any]] = []
        for group in groups:
            # URL 있는 항목 우선
            with_url = [i for i in group if items[i].get(self.url_field, "").strip()]
            chosen_idx = with_url[0] if with_url else group[0]
            chosen = dict(items[chosen_idx])

            # 같은 그룹의 다른 URL을 alt_links로 병합 (정보 손실 방지)
            alt_links = [
                items[i][self.url_field]
                for i in group
                if i != chosen_idx and items[i].get(self.url_field, "").strip()
            ]
            if alt_links:
                chosen["alt_links"] = alt_links

            result.append(chosen)

        return result

    def find_duplicates(self, items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """중복 그룹만 반환 (디버깅/검토용). 단일 항목 그룹 제외."""
        texts = [str(item.get(self.key_field, "")) for item in items]
        groups = _group_duplicates(texts, self.threshold)
        return [
            [items[i] for i in group]
            for group in groups
            if len(group) > 1
        ]


# ── 텍스트 리스트 전용 헬퍼 ────────────────────────────────────────────────────

def deduplicate_strings(texts: list[str], threshold: float = SIMILARITY_THRESHOLD) -> list[str]:
    """단순 문자열 리스트 중복 제거 (폴더명/키워드 정리용)."""
    if not texts:
        return []
    groups = _group_duplicates(texts, threshold)
    return [texts[group[0]] for group in groups]
