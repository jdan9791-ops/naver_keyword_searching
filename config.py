import os

# ─── Naver API ────────────────────────────────────────────────────────────────
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/webkr.json"
NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"

# ─── 검색 설정 ────────────────────────────────────────────────────────────────
SEARCH_DISPLAY = 100          # 검색 결과 최대 개수 (Naver API max: 100)
SEARCH_START = 1

# ─── 중복 제거 설정 ───────────────────────────────────────────────────────────
# 유사도 이 값 이상이면 중복으로 간주 (0.0 ~ 1.0)
SIMILARITY_THRESHOLD = 0.75

# ─── URL 체크 설정 ────────────────────────────────────────────────────────────
URL_TIMEOUT = 10              # 초
URL_CHECK_CONCURRENCY = 10   # 동시 체크 수
MAX_REDIRECTS = 5

# ─── 출력 경로 ────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "results")

# ─── 필터 설정 ────────────────────────────────────────────────────────────────
# 이 단어가 제목/설명에 포함되면 결과에서 제외 (법률사무소 정보 제거)
EXCLUDE_KEYWORDS = [
    "법률사무소", "법무법인", "변호사", "로펌", "law firm",
    "법률 사무소", "법무 법인",
]

# 사기사이트/거래소 관련 키워드 (URL 수집 우선순위 상향)
SCAM_PRIORITY_KEYWORDS = [
    "사기", "사기사이트", "사기거래소", "피해", "환급", "출금불가",
    "먹튀", "코인사기", "투자사기", "리딩사기", "보이스피싱",
]
