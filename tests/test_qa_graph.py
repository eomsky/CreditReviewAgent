import asyncio

from app.domain.evidence import Evidence, EvidenceSourceType
from app.graphs.qa_graph import MAX_RETRIEVAL_COUNT, QADeps, run_qa, stream_qa
from app.graphs.qa_graph import _generator_messages


class FakeLLM:
    def __init__(self, responses, stream_tokens=None):
        self.responses = iter(responses)
        self.stream_tokens = stream_tokens or ["근거 ", "답변"]

    async def complete(self, messages, max_tokens=1024):
        return next(self.responses)

    async def stream(self, messages, max_tokens=1024):
        for token in self.stream_tokens:
            yield token


class FakeRetrieval:
    def __init__(self):
        self.calls = 0

    def retrieve(self, question, *, case_id, extra_queries=None):
        self.calls += 1
        item = Evidence(f"e:{self.calls}", EvidenceSourceType.CASE_DOCUMENT, "doc", case_id, "심사자료", "부채비율 120%")
        return [item], "predefined:test"

    def find_conflicts(self, evidence):
        return []


def run_with(responses):
    retrieval = FakeRetrieval()
    result = asyncio.run(run_qa("부채비율을 검토해줘", deps=QADeps(FakeLLM(responses), retrieval)))
    return result, retrieval


def test_conditional_revision_then_approval():
    result, retrieval = run_with([
        "부채비율은 120%입니다. [e:1]",
        '{"approved":false,"issues":[{"type":"writing_issue","message":"표현 수정"}],"missing_evidence_queries":[]}',
        "근거상 부채비율은 120%입니다. [e:1]",
        '{"approved":true,"issues":[],"missing_evidence_queries":[]}',
    ])
    assert result["approved"] is True
    assert result["revision_count"] == 1
    assert result["workflow_status"] == "approved"
    assert retrieval.calls == 1


def test_insufficient_evidence_routes_to_bounded_retrieval():
    result, retrieval = run_with([
        "근거 부족",
        '{"approved":false,"issues":[{"type":"insufficient_evidence","message":"추가 자료 필요"}],"missing_evidence_queries":["최근 재무제표"]}',
        "재검색 근거 답변",
        '{"approved":false,"issues":[{"type":"insufficient_evidence","message":"여전히 부족"}],"missing_evidence_queries":[]}',
    ])
    assert retrieval.calls == MAX_RETRIEVAL_COUNT
    assert result["workflow_status"] == "needs_human_review"
    assert result["retrieval_count"] == MAX_RETRIEVAL_COUNT


def test_malformed_validator_output_requires_human_review():
    result, _ = run_with(["초안", "not-json"])
    assert result["workflow_status"] == "needs_human_review"
    assert "validation_failure" in result["issue_types"]


def test_stream_and_non_stream_use_same_graph_result():
    responses = ['{"approved":true,"issues":[],"missing_evidence_queries":[]}']
    deps = QADeps(FakeLLM(responses, ["첫 ", "토큰 ", "응답"]), FakeRetrieval())

    async def collect():
        return [event async for event in stream_qa("질문", deps=deps)]

    events = asyncio.run(collect())
    assert events[-1]["type"] == "done"
    assert events[-1]["result"]["workflow_status"] == "approved"
    token_events = [event for event in events if event["type"] == "token"]
    assert [event["content"] for event in token_events] == ["첫 ", "토큰 ", "응답"]
    assert all(event["replace"] is False for event in token_events)
    validate_index = next(index for index, event in enumerate(events) if event.get("stage") == "validate")
    assert events.index(token_events[0]) < validate_index


def test_chat_mode_is_concise_while_review_mode_remains_structured():
    base = {"question": "신청금액만 알려줘", "evidence_context": "신청금액 50억원"}
    chat_prompt = _generator_messages({**base, "response_mode": "chat"})[-1]["content"]
    review_prompt = _generator_messages({**base, "response_mode": "review"})[-1]["content"]
    assert "1~3문장" in chat_prompt
    assert "고정 양식을 강제하지 마세요" in chat_prompt
    assert "공식 심사의견 작성 요청" in review_prompt
    assert "상환능력" in review_prompt
