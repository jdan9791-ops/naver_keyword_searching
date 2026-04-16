# Naver 키워드 검색 도구 - 프로젝트 메모

## 현재 상태
- **브랜치**: `claude/apply-additional-fixes-c8DV7`
- **커밋**: `5ec4806` - 초기 구현 완료, 원격 푸시됨
- **저장소**: `jdan9791-ops/naver_keyword_searching`

## 구현 완료된 파일 (8개, 1,111줄)
- `config.py` - 설정 (API키, 유사도 임계값 0.75, URL 타임아웃, 제외/우선 키워드)
- `naver_searcher.py` - Naver Open API 웹/뉴스/블로그 통합 검색
- `deduplicator.py` - 한국어 중복 제거 (공백 정규화 + SequenceMatcher + Jaccard)
- `url_checker.py` - URL 접근 가능 여부 병렬 체크
- `result_processor.py` - 법률사무소 항목 제거, 사기URL 우선 정렬
- `folder_manager.py` - 키워드별 폴더 저장/관리/중복정리
- `main.py` - CLI 진입점 (search / dedup / check-urls / summary)
- `requirements.txt` - requests>=2.31.0

## 사용자 요구사항 (반영 완료)
1. **URL 접근 확인** - 사이트 주소 오픈 여부 체크
2. **중복 필터링** - 의미 유사 항목 및 띄어쓰기 차이 항목 제거
   - '도산 신탁 프로젝트' == '도산신탁프로젝트' (공백 차이)
   - '당신의 자산 거래 동반자' ≈ '당신의 자산 거래 파트너' (유사도 75%)
3. **법률사무소 제거** - 소재만 중요, 사기사이트/거래소 URL 우선 수집

## 다음 할 일 (미완료)
- **Google Drive 연동 필요**: 출력 폴더가 Google Drive
  - Google Drive MCP 커넥터가 연결되었으나, 이전 세션에서 도구 미인식
  - 새 대화에서 Google Drive MCP 도구 사용 가능 여부 확인 필요
  - 사용 가능 도구: create_file, download_file_content, get_file_metadata, get_file_permissions, list_recent_files, read_file_content, search_files
- **기존 Google Drive 폴더 삭제 후 4월 15일 기준으로 재생성**
- Naver API 환경변수 설정 확인 (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)
