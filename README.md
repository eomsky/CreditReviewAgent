# Credit Review Assistant

Codespaces에서 FastAPI, SQLite, Chroma, LangGraph를 실행하고 Google Colab의
`Qwen2.5-VL-32B-Instruct-AWQ` vLLM 서버를 호출하는 멀티모달 여신심사 지원 시스템입니다.

## Architecture

```text
Browser / API client
        |
        v
FastAPI (Codespaces)
  |-- SQLite: 기업, 문서, 작업, 재무 데이터, 보고서, 감사 이력
  |-- Local storage: PDF, 이미지, Excel 원본
  |-- Chroma: 문서 청크와 임베딩 검색 색인
  |-- LangGraph: 문서 수집 및 여신심사 워크플로
  `-- Colab vLLM: 텍스트·이미지 분석과 보고서 생성
```

SQLite에는 원본 청크와 메타데이터를 보관하고 Chroma는 재생성 가능한 검색 색인으로
취급합니다. 모든 런타임 데이터는 저장소의 `data/` 아래에 저장되므로 Codespace 정지와
컨테이너 재빌드 후에도 유지됩니다. Codespace 자체를 삭제하면 함께 삭제됩니다.

## Directory structure

```text
app/
|-- api/                    # FastAPI 라우터, 의존성, 예외 처리
|   `-- v1/endpoints/       # documents, search, reports, health
|-- clients/                # Colab vLLM HTTP/OpenAI 호환 클라이언트
|-- core/                   # 설정, 경로, 로깅, 보안, 공통 예외
|-- database/               # SQLite 엔진, SQLAlchemy 모델, Alembic
|-- domain/                 # 프레임워크 독립 도메인 모델과 enum
|-- graphs/
|   |-- ingestion/          # 파일 검증→저장→추출→청킹→인덱싱
|   `-- credit_review/      # 검색→재무분석→생성→검증→저장
|-- ingestion/              # PDF/이미지/문서 로더와 청커
|-- llm/                    # 모델 팩토리, 프롬프트, 구조화 출력
|-- rag/                    # 임베딩, Chroma, 검색기, 재색인
|-- repositories/           # DB 접근 계층
|-- schemas/                # API 요청·응답 Pydantic 모델
|-- storage/                # 원본 파일 저장소 인터페이스/로컬 구현
|-- tools/                  # 재무비율과 신용위험의 결정론적 계산
`-- workers/                # 장시간 문서 처리 작업 실행 계층

data/
|-- database/               # SQLite DB, WAL, SHM
|-- vector_db/              # Chroma PersistentClient 데이터
|-- uploads/                # UUID 기반 원본 파일
|-- processed/              # 추출 텍스트, 표, 페이지 이미지
`-- backups/                # SQLite/Chroma/업로드 백업
```

## Planned API

```text
POST   /api/v1/documents
GET    /api/v1/documents/{document_id}
GET    /api/v1/documents/{document_id}/status
DELETE /api/v1/documents/{document_id}
POST   /api/v1/documents/{document_id}/reindex
POST   /api/v1/search
POST   /api/v1/reports/generate
GET    /api/v1/health
```

## Local setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

초기 SQLite 운영에서는 동시 쓰기 충돌을 피하기 위해 Uvicorn worker 하나를 사용합니다.

