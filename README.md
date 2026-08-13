# Credit Review Agent POC

Codespaces의 FastAPI 애플리케이션과 Colab의 Qwen2.5-VL-32B vLLM 서버를 연결한 여신심사 지원 POC입니다.

## 구현 기능

- SQLite에 180개 기업, 4개년 재무정보, 다수 여신계좌를 재현 가능한 가상 데이터로 생성
- 읽기 전용 allow-list 기반 Text-to-SQL과 문서 RAG를 함께 사용
- PDF, DOCX, XLSX, TXT 및 이미지 업로드·추출·영구 저장
- LangGraph 생성 에이전트 A → 검증 에이전트 B → 수정 답변 흐름
- 욕설, 공격적 표현, 불법·개인정보 침해 요청 가드레일
- 대화, 사용자 질문, 최종 답변, 첨부파일 및 검증 메타데이터 저장
- 검증이 끝난 최종 답변의 스트리밍 표시

## 실행

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m scripts.seed_poc
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

`python -m scripts.seed_poc`은 다음 샘플 문서를 `data/sample_documents/`에 생성하고 검색 인덱스에 적재합니다.

- 여신심사 운영지침 PDF
- 업종별 리스크 가이드 DOCX
- 담보평가 체크리스트 DOCX
- 여신정책 정량기준 XLSX

## 주요 API

```text
GET  /api/v1/health
GET  /api/v1/poc/stats
POST /api/v1/chat/completions
POST /api/v1/chat/completions/stream
```

브라우저 클라이언트는 JSON 안에 대화와 Base64 첨부파일을 넣어 스트리밍 API를 호출합니다. SQLite와 업로드 파일은 `data/` 아래에 저장되므로 Codespace가 유지되는 동안 재시작 후에도 남습니다.

## 검증

```bash
pytest -q
python -m compileall -q app scripts tests
node --check app/web/app.js
```
