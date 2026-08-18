from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "web" / "app.js").read_text(encoding="utf-8")
CHAT_CSS = (ROOT / "app" / "web" / "chat-fixes.css").read_text(encoding="utf-8")


def test_review_workbench_removes_redundant_account_header():
    assert "loan-context" not in HTML
    assert "여신신청번호" not in HTML
    assert 'id="dataStatusButton"' in HTML
    assert "에이전트 심사의견" in HTML
    assert "CREDIT REVIEW" not in HTML
    assert "AI 심사 대화" not in HTML
    assert "추가 정보나 검토 방향을 말씀해 주세요." in HTML


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


def test_streaming_stop_button_remains_clickable():
    assert '.composer.busy #sendButton' in CHAT_CSS
    assert 'pointer-events: auto' in CHAT_CSS
    assert 'state.abort?.abort()' in JS


def test_sentence_level_evidence_popover_and_source_viewer_exist():
    assert 'id="citationPopover"' in HTML
    assert 'id="sourceViewerDialog"' in HTML
    assert "evidence-claim" in JS
    assert "data-open-evidence" in JS
    assert "openSourceViewer" in JS
    assert "moveEvidence" in JS
    assert "evidence-highlight" in CHAT_CSS
    assert "table-evidence-view" in CHAT_CSS


def test_screen_catalog_and_clipboard_images_are_sent_to_agent():
    assert "data_catalog:sourceCatalog()" not in JS
    assert "screen_context:screenContext()" in JS
    assert 'addEventListener("paste"' in JS
    assert 'item.type.startsWith("image/")' in JS


def test_review_stream_uses_completed_result_and_preserves_structure():
    assert 'event.type==="done"' in JS
    assert "if(!completed)throw Error" in JS
    assert "validateCompleteReview(answer)" in JS
    assert "renderOpinionBody" in JS
    assert "###\\s+" in JS


def test_input_data_catalog_is_loaded_from_server_without_fixed_twelve_sources():
    assert "const baseSources" not in JS
    assert "loadDataCatalog" in JS
    assert "/api/v1/poc/data-catalog" in JS
    assert 'id="dataCountBadge">0<' in HTML
    assert "state.sources=[...items" in JS


def test_chat_request_does_not_resend_catalog_rows_or_samples():
    assert "function sourceCatalog()" not in JS
    assert "sample_rows" not in JS
    assert "screen_context:screenContext()" in JS
