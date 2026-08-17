# CreditReviewAgent 운영 지향 아키텍처

## 실제 호출 경로

`API → guardrail/authorization → LangGraph → RetrievalService → Repository → SQLite/FTS5/Chroma`

LangGraph가 비스트리밍·스트리밍 실행의 단일 source of truth다. 노드는
`retrieve → generate → validate`이며 검증 결과에 따라 `revise`, 추가 `retrieve`,
`human`, `finalize`로 이동한다. revision/retrieval 횟수는 Python에서 제한한다.

## 근거와 검증

- DB, 문서, 첨부자료는 `Evidence`로 정규화한다.
- 답변은 evidence ID를 인용하도록 프롬프트에서 요구한다.
- validator는 명시적인 JSON schema를 사용하며 malformed output은 자동 승인하지 않는다.
- 수치 검사는 deterministic validator를 먼저 적용한다.
- actual과 forecast는 별도 value type이므로 충돌로 취급하지 않는다.
- 미해결 충돌, 검증 불가, 반복 한도 초과는 `needs_human_review`로 종료한다.

## 데이터 경계

- 원본: `UPLOAD_DIR`
- 업무·감사 metadata/정형 데이터: SQLite
- lexical chunks: SQLite FTS5
- vector chunks: persistent Chroma
- 모든 검색은 authorization 후 case metadata filter를 적용한다.
- 문서 삭제는 원본, RDB, FTS, chunk metadata, Chroma를 함께 제거한다.

## 비파괴 마이그레이션

애플리케이션 시작 시 기존 SQLite에 `documents.status/version`,
`document_chunk_metadata`, `case_access`를 추가한다. 기존 테이블이나 데이터를 삭제하지 않는다.
기존 case는 UI 호환을 위해 `poc-user` owner 권한이 자동 부여된다.

## 현재 구현과 운영 전 교체점

현재 구현:

- SQLite 단일 프로세스 PoC
- 기본 principal `poc-user`
- deterministic hashing embedding + Chroma
- 요청 내 동기 ingestion, 단계별 상태 저장
- predefined financial query 우선, legacy SELECT guard 유지

운영 전 필수 교체/확인:

- SSO principal/org/role 기반 case ACL과 관리자 정책
- DB read-only 계정 및 허용 view, statement timeout, connection pool 제한
- BGE-M3 등 승인된 embedding과 오프라인 품질 평가
- ingestion queue/worker 및 재시도·dead-letter 정책
- 조직별 source priority 정책과 중요 metric catalog
- 감사 로그 보존·마스킹·접근권한·SIEM 전송 정책
- Chroma backup/restore 및 SQLite에서 운영 RDB로의 migration rehearsal

## 검색 평가

`app.rag.evaluation.evaluate_rankings`에서 Hit@K, Recall@K, MRR을 계산한다.
평가셋은 질문, 정답 document/chunk ID, case ID를 포함해야 하며 generation 평가는 별도로 수행한다.
