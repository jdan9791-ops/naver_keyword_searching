import os
from pathlib import Path

# .env 파일 자동 로드 (setup_drive.py가 생성)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

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

# 키워드 이력 파일 (results 폴더와 별도로 누적 관리)
KEYWORD_HISTORY_FILE = os.environ.get("KEYWORD_HISTORY_FILE", "keyword_history.json")

# ─── Google Drive 설정 ────────────────────────────────────────────────────────
# Google Drive 동기화 활성화 여부 (credentials.json이 있어야 동작)
GOOGLE_DRIVE_ENABLED = os.environ.get("GOOGLE_DRIVE_ENABLED", "false").lower() == "true"

# 업로드할 Google Drive 루트 폴더 ID
# Drive 폴더 URL에서 마지막 경로 부분: https://drive.google.com/drive/folders/{FOLDER_ID}
# 비워두면 내 드라이브 최상위에 저장
GOOGLE_DRIVE_ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")

# OAuth2 credentials.json 경로 (Google Cloud Console에서 다운로드)
GOOGLE_DRIVE_CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_DRIVE_CREDENTIALS_FILE", "credentials.json"
)

# 인증 토큰 저장 경로 (첫 인증 후 자동 생성)
GOOGLE_DRIVE_TOKEN_FILE = os.environ.get("GOOGLE_DRIVE_TOKEN_FILE", "token.json")

# ─── 필터 설정 ────────────────────────────────────────────────────────────────
# 이 단어가 제목/설명/블로거명에 포함되면 결과에서 제외 (법률사무소 정보 제거)
EXCLUDE_KEYWORDS = [
    # 기관명
    "법률사무소", "법무법인", "법률 사무소", "법무 법인", "로펌", "law firm",
    # 직함
    "변호사", "법무사", "검사출신", "판사출신", "전관",
    # 서비스 홍보
    "무료상담", "법률상담", "피해상담", "형사상담", "법률 상담",
    "형사고소", "법적대응", "형사전문", "민사전문",
    "피해구제", "소송", "고소장", "내용증명",
]

# 사기사이트/거래소 관련 키워드 (URL 수집 우선순위 상향)
SCAM_PRIORITY_KEYWORDS = [
    "사기", "사기사이트", "사기거래소", "피해", "환급", "출금불가",
    "먹튀", "코인사기", "투자사기", "리딩사기", "보이스피싱",
]
