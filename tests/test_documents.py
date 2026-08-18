from app.services.documents import is_company_relevant


def test_company_relevance_accepts_only_target_company_mentions():
    assert is_company_relevant("A기업 2025년 재무제표", "재무제표.pdf", "A기업")
    assert is_company_relevant("주식회사 에이모터스의 수주 내역", "자료.pdf", "(주)에이모터스")
    assert not is_company_relevant("글로벌 자동차 산업 판매 동향", "자동차 산업 보고서.pdf", "A기업")
    assert not is_company_relevant("B기업 매출액 1,680억원", "B기업_재무.pdf", "A기업")
