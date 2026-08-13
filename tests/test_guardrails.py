from app.services.guardrails import check_input


def test_abusive_question_is_blocked():
    result = check_input("야 이 병신아 대출 승인해")
    assert not result.allowed
    assert result.category == "abusive_language"


def test_normal_credit_question_is_allowed():
    assert check_input("부채비율이 높은 기업의 위험을 알려줘").allowed
