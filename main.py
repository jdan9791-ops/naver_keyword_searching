"""
Naver 키워드 검색 도구 - 메인 진입점

사용법
──────
# 키워드 목록으로 검색
python main.py search --keywords "사기거래소A" "코인사기B" --check-urls

# 기존 결과 폴더 중복 정리
python main.py dedup --keyword "사기거래소A"

# 모든 폴더 중복 정리 + 유사 폴더명 검사
python main.py dedup --all

# URL 접근 가능 여부만 재검사
python main.py check-urls --keyword "사기거래소A"

# 전체 현황 요약
python main.py summary
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from config import OUTPUT_DIR, SIMILARITY_THRESHOLD
from deduplicator import KoreanDeduplicator
from folder_manager import FolderManager
from naver_searcher import NaverSearcher, NaverSearchError
from result_processor import ResultProcessor
from url_checker import check_urls_batch, filter_accessible_items
from whois_checker import attach_whois_to_items, check_whois_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── 서브커맨드 ────────────────────────────────────────────────────────────────

def cmd_search(args: argparse.Namespace) -> None:
    """키워드 검색 → 중복 제거 → URL 체크 → 저장."""
    try:
        searcher = NaverSearcher()
    except NaverSearchError as exc:
        logger.error(str(exc))
        sys.exit(1)

    processor = ResultProcessor(remove_law_firms=not args.keep_law_firms)
    deduper = KoreanDeduplicator(threshold=args.threshold)
    fm = FolderManager(base_dir=args.output)

    for keyword in args.keywords:
        logger.info("═" * 50)
        logger.info("검색 키워드: '%s'", keyword)

        # 1. 검색
        raw = searcher.search_all(keyword)
        logger.info("원본 결과: %d건", len(raw))

        # 2. 후처리 (HTML 제거, 법률사무소 필터, 정렬)
        processed = processor.process(raw)

        # 3. 중복 제거
        deduped = deduper.deduplicate(processed)
        logger.info("중복 제거 후: %d건", len(deduped))

        # 4. URL 접근 가능 여부 체크
        if args.check_urls:
            logger.info("URL 접근 확인 중...")
            urls = [item.get("link", "") for item in deduped]
            statuses = check_urls_batch([u for u in urls if u])
            deduped = filter_accessible_items(deduped, statuses=statuses)
            inaccessible = sum(1 for s in statuses.values() if not s.accessible)
            if inaccessible:
                logger.warning("접근 불가 URL %d개 제외됨", inaccessible)

        # 5. Whois 도메인 등록일 조회
        if args.whois:
            logger.info("도메인 등록일 조회 중...")
            urls = [item.get("link", "") for item in deduped if item.get("link", "").strip()]
            whois_results = check_whois_batch(urls)
            deduped = attach_whois_to_items(deduped, results=whois_results)
            found = sum(1 for r in whois_results.values() if r.reg_date)
            logger.info("도메인 등록일 조회 완료: %d/%d건", found, len(whois_results))

        # 6. 사기 URL 추출
        scam_urls = processor.get_scam_urls(deduped)
        report = processor.report(deduped)

        # 6. URL 없는 항목 경고
        no_url_items = [i for i in deduped if not i.get("link", "").strip()]
        if no_url_items:
            logger.warning(
                "URL 없는 항목 %d건 (전체의 %.1f%%)",
                len(no_url_items),
                len(no_url_items) / len(deduped) * 100 if deduped else 0,
            )

        # 7. 저장
        folder = fm.save_results(keyword, deduped, scam_urls=scam_urls, report=report)
        logger.info("저장 완료: %s", folder)
        logger.info(
            "요약 → 전체:%d  URL있음:%d  URL없음:%d  사기URL:%d",
            report["total"], report["with_url"], report["without_url"], len(scam_urls),
        )


def cmd_dedup(args: argparse.Namespace) -> None:
    """기존 결과 폴더 중복 정리."""
    fm = FolderManager(base_dir=args.output)

    if args.all:
        # 폴더명 수준 유사도 검사
        pairs = fm.deduplicate_keyword_folders(threshold=args.threshold)
        if pairs:
            print("\n⚠️  유사 폴더명 발견 (수동 확인 필요):")
            for a, b in pairs:
                print(f"  '{a}' ≈ '{b}'")

        # 각 폴더 내 항목 중복 제거
        for keyword in fm.list_keywords():
            result = fm.deduplicate_folder(keyword, threshold=args.threshold)
            print(
                f"  [{keyword}] {result['before']} → {result['after']}건 "
                f"(-{result['removed']})"
            )
    elif args.keyword:
        result = fm.deduplicate_folder(args.keyword, threshold=args.threshold)
        print(
            f"[{args.keyword}] {result['before']} → {result['after']}건 "
            f"(-{result['removed']})"
        )
    else:
        print("--keyword 또는 --all 옵션을 사용하세요.")


def cmd_check_urls(args: argparse.Namespace) -> None:
    """저장된 결과의 URL 접근 가능 여부 재검사."""
    fm = FolderManager(base_dir=args.output)
    keywords = [args.keyword] if args.keyword else fm.list_keywords()

    for keyword in keywords:
        items = fm.load_results(keyword)
        if not items:
            continue

        urls = [item.get("link", "") for item in items if item.get("link", "").strip()]
        logger.info("'%s': URL %d개 체크 중...", keyword, len(urls))
        statuses = check_urls_batch(urls)

        accessible = sum(1 for s in statuses.values() if s.accessible)
        inaccessible = sum(1 for s in statuses.values() if not s.accessible)

        print(f"\n[{keyword}]")
        print(f"  ✅ 접근 가능: {accessible}개")
        print(f"  ❌ 접근 불가: {inaccessible}개")

        if args.verbose:
            for url, status in statuses.items():
                print(f"    {status.summary:30s} {url}")

        # URL 없는 항목 별도 출력
        no_url = sum(1 for i in items if not i.get("link", "").strip())
        if no_url:
            print(f"  ⚠️  URL 없음: {no_url}개")


def cmd_summary(args: argparse.Namespace) -> None:
    """전체 현황 요약 출력."""
    fm = FolderManager(base_dir=args.output)
    summaries = fm.summary()

    if not summaries:
        print("저장된 결과 없음.")
        return

    print(f"\n{'키워드':<30} {'전체':>5} {'URL있음':>7} {'URL없음':>7} {'사기URL':>7}")
    print("─" * 60)
    for s in summaries:
        print(
            f"{s['keyword']:<30} {s['total']:>5} {s['with_url']:>7} "
            f"{s['without_url']:>7} {s['scam_urls']:>7}"
        )
    print("─" * 60)
    total_items = sum(s["total"] for s in summaries)
    total_with_url = sum(s["with_url"] for s in summaries)
    print(
        f"{'합계':<30} {total_items:>5} {total_with_url:>7} "
        f"{total_items - total_with_url:>7}"
    )


# ── CLI 파서 ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Naver 키워드 검색 · 중복 제거 · URL 확인 도구"
    )
    parser.add_argument(
        "--output", default=OUTPUT_DIR, help=f"결과 저장 경로 (기본: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=SIMILARITY_THRESHOLD,
        help=f"유사도 임계값 (기본: {SIMILARITY_THRESHOLD})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p_search = sub.add_parser("search", help="키워드 검색 및 저장")
    p_search.add_argument("--keywords", nargs="+", required=True, help="검색 키워드 목록")
    p_search.add_argument(
        "--check-urls", action="store_true", help="검색 후 URL 접근 가능 여부 확인"
    )
    p_search.add_argument(
        "--keep-law-firms", action="store_true", help="법률사무소 결과 제거하지 않음"
    )
    p_search.add_argument(
        "--whois", action="store_true", help="도메인 등록일(생성일) Whois 조회"
    )

    # dedup
    p_dedup = sub.add_parser("dedup", help="중복 제거")
    p_dedup.add_argument("--keyword", help="특정 키워드 폴더만 처리")
    p_dedup.add_argument("--all", action="store_true", help="모든 폴더 처리")

    # check-urls
    p_check = sub.add_parser("check-urls", help="URL 접근 가능 여부 재검사")
    p_check.add_argument("--keyword", help="특정 키워드 폴더만 검사")
    p_check.add_argument("--verbose", "-v", action="store_true", help="URL별 상세 출력")

    # summary
    sub.add_parser("summary", help="전체 저장 현황 요약")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "search": cmd_search,
        "dedup": cmd_dedup,
        "check-urls": cmd_check_urls,
        "summary": cmd_summary,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
