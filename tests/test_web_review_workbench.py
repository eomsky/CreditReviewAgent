from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "web" / "app.js").read_text(encoding="utf-8")


def test_review_workbench_removes_redundant_account_header():
    assert "loan-context" not in HTML
    assert "여신신청번호" not in HTML
    assert 'id="dataStatusButton"' in HTML
    assert "AI 심사 대화" in HTML


def test_opinion_confirmation_stream_and_versions_exist():
    assert 'id="previousOpinionVersion"' in HTML
    assert 'id="nextOpinionVersion"' in HTML
    assert "현재까지 내용 반영" in HTML
    assert "반영내용 보완" in JS
    assert "V${pendingId} · 생성 중" in JS
    assert "renderOpinion(text,{streaming:true})" in JS


def test_dynamic_sections_retain_credit_review_guardrails():
    assert "고정된 목차를 기계적으로 사용하지 말고" in JS
    assert "상환능력과 근거" in JS
    assert "주요 위험요인과 보완방안" in JS
    assert "최종 종합의견" in JS


def test_data_explorer_is_sortable_and_read_only():
    assert 'data-sort="name"' in HTML
    assert 'data-sort="type"' in HTML
    assert 'data-sort="status"' in HTML
    assert "READ ONLY" in JS
    assert "SELECT * FROM" in JS


def test_chat_and_review_modes_are_separate_and_long_answers_expand():
    assert 'responseMode="chat"' in JS
    assert '"review"' in JS
    assert "대화 더보기" in JS
