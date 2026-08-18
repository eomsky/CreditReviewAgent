import asyncio

from app.domain.evidence import Evidence, EvidenceSourceType
from app.graphs.qa_graph import MAX_RETRIEVAL_COUNT, QADeps, run_qa, stream_qa
from app.graphs.qa_graph import _generation_budget, _generator_messages, _parse_intent_brief


INTENT = '{"user_goal":"부채비율 검토","requested_output":"근거 기반 답변","target_entities":["부채비율"],"required_evidence":["재무자료"],"excluded_context":[],"must_answer_directly":true,"ambiguity":null,"retrieval_queries":["부채비율"]}'


class FakeLLM:
    def __init__(self, responses, stream_tokens=None):
        self.responses = iter(responses)
        self.stream_tokens = stream_tokens or ["근거 ", "답변"]
        self.last_finish_reason = None
        self.max_tokens_used = []

    async def complete(self, messages, max_tokens=1024):
        self.max_tokens_used.append(max_tokens)
        self.last_finish_reason = "stop"
        return next(self.responses)

    async def stream(self, messages, max_tokens=1024):
        self.max_tokens_used.append(max_tokens)
        for token in self.stream_tokens:
            yield token
        self.last_finish_reason = "stop"


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
    result = asyncio.run(run_qa("부채비율을 검토해줘", deps=QADeps(FakeLLM([INTENT, *responses]), retrieval), response_mode="review"))
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
    responses = [INTENT, '{"approved":true,"issues":[],"missing_evidence_queries":[]}']
    deps = QADeps(FakeLLM(responses, ["첫 ", "토큰 ", "응답"]), FakeRetrieval())

    async def collect():
        return [event async for event in stream_qa("질문", deps=deps, response_mode="review")]

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
    assert "일반 대화" in chat_prompt
    assert "가장 적합한 방식을 스스로 선택" in chat_prompt
    assert "공식 심사의견 작성 요청" in review_prompt
    assert "상환능력" in review_prompt


def test_chat_mode_validates_alignment_with_interpreted_intent():
    intent = '{"user_goal":"신청금액 확인","requested_output":"금액만 간결하게","target_entities":["신청금액"],"required_evidence":["신청정보"],"excluded_context":["심사의견 요약"],"must_answer_directly":true,"ambiguity":null,"retrieval_queries":["신청금액"]}'
    deps = QADeps(FakeLLM([
        intent,
        "신청금액은 50억원입니다.",
        '{"approved":true,"issues":[],"missing_evidence_queries":[]}',
    ]), FakeRetrieval())
    result = asyncio.run(run_qa("신청금액이 얼마야?", deps=deps, response_mode="chat"))
    assert result["final_answer"] == "신청금액은 50억원입니다."
    assert result["workflow_status"] == "approved"
    assert result["approved"] is True
    assert result["intent_brief"]["excluded_context"] == ["심사의견 요약"]


def test_chat_misalignment_is_revised_before_returning():
    intent = '{"user_goal":"현재 조회 가능한 테이블 목록 확인","requested_output":"테이블명 목록","target_entities":["DB 테이블"],"required_evidence":["데이터 카탈로그"],"excluded_context":["현재 심사의견"],"must_answer_directly":true,"ambiguity":null,"retrieval_queries":["데이터 카탈로그 테이블"]}'
    deps = QADeps(FakeLLM([
        intent,
        "사업 및 거래 현황을 설명하겠습니다.",
        '{"approved":false,"issues":[{"type":"question_misalignment","message":"테이블 목록에 답하지 않음"}],"missing_evidence_queries":[]}',
        "현재 조회 가능한 테이블은 companies, financials, loans입니다.",
        '{"approved":true,"issues":[],"missing_evidence_queries":[]}',
    ]), FakeRetrieval())
    result = asyncio.run(run_qa("현재 참조하고 있는 테이블 리스트를 보여줘", deps=deps, response_mode="chat"))
    assert result["revision_count"] == 1
    assert "companies" in result["final_answer"]
    assert result["workflow_status"] == "approved"


def test_malformed_intent_falls_back_to_original_question():
    brief = _parse_intent_brief("not-json", "현재 자료를 알려줘")
    assert brief["user_goal"] == "현재 자료를 알려줘"
    assert brief["retrieval_queries"] == ["현재 자료를 알려줘"]


def test_review_prompt_requires_complete_markdown_sections():
    prompt = _generator_messages({
        "question": "심사의견을 갱신해줘",
        "evidence_context": "근거",
        "response_mode": "review",
    })[-1]["content"]
    assert "## 소제목" in prompt
    assert "모든 섹션과 종합의견을 완결" in prompt


def test_intent_controls_detail_raw_data_completion_and_budget():
    brief = _parse_intent_brief(
        '{"user_goal":"자료 상세 분석","requested_output":"상세 보고서","detail_level":"detailed","include_raw_data":true,"completion_criteria":["표본 3건 포함","결론 완결"],"response_budget":1600}',
        "자료를 분석해줘",
    )
    assert brief["detail_level"] == "detailed"
    assert brief["include_raw_data"] is True
    assert brief["completion_criteria"] == ["표본 3건 포함", "결론 완결"]
    assert _generation_budget({"intent_brief": brief, "response_mode": "chat"}) == 1600
    assert _generation_budget({"intent_brief": brief, "response_mode": "review"}) == 1800


def test_generator_blocks_raw_dumps_unless_intent_requests_them():
    state = {
        "question": "현재 테이블 목록을 알려줘",
        "evidence_context": "companies 180건, financials 720건, loans 360건",
        "response_mode": "chat",
        "intent_brief": {
            "user_goal": "현재 테이블 목록 확인",
            "requested_output": "이름과 건수의 간결한 목록",
            "detail_level": "brief",
            "include_raw_data": False,
            "completion_criteria": ["테이블명과 건수를 포함"],
            "response_budget": 400,
        },
    }
    prompt = _generator_messages(state)[-1]["content"]
    assert "Do not print raw rows" in prompt
    assert '"detail_level": "brief"' in prompt
    assert '"include_raw_data": false' in prompt


def test_length_finish_reason_forces_compact_revision():
    intent = '{"user_goal":"테이블 목록 확인","requested_output":"이름과 건수","detail_level":"brief","include_raw_data":false,"completion_criteria":["세 테이블을 모두 포함","문장을 완결"],"response_budget":400}'
    llm = FakeLLM([
        intent,
        "companies의 전체 원시 데이터는 다음과 같습니다...",
        '{"approved":true,"issues":[],"missing_evidence_queries":[]}',
        "현재 테이블은 companies, financials, loans입니다.",
        '{"approved":true,"issues":[],"missing_evidence_queries":[]}',
    ])
    original_complete = llm.complete
    calls = 0

    async def complete_with_first_generation_cutoff(messages, max_tokens=1024):
        nonlocal calls
        result = await original_complete(messages, max_tokens)
        calls += 1
        llm.last_finish_reason = "length" if calls == 2 else "stop"
        return result

    llm.complete = complete_with_first_generation_cutoff
    result = asyncio.run(run_qa("현재 테이블 목록을 알려줘", deps=QADeps(llm, FakeRetrieval()), response_mode="chat"))
    assert result["revision_count"] == 1
    assert result["generation_finish_reason"] == "stop"
    assert result["final_answer"].endswith("입니다.")
