"""Deterministic, database-grounded V1 review for the seeded demonstration case."""

from __future__ import annotations

from typing import Any

from app.database.poc_store import connect


def _won(value: float | int | None) -> str:
    return f"{float(value or 0) / 100:,.0f}억원"


def build_initial_review(case_id: str) -> dict[str, Any]:
    with connect() as connection:
        company = connection.execute(
            """SELECT c.* FROM review_cases rc JOIN companies c ON c.name=rc.company_name
            WHERE rc.id=? LIMIT 1""", (case_id,)
        ).fetchone()
        if not company:
            return {"text": "", "sources": []}
        company_id = company["id"]
        financials = connection.execute(
            "SELECT * FROM financials WHERE company_id=? ORDER BY fiscal_year DESC LIMIT 2",
            (company_id,),
        ).fetchall()
        application = connection.execute(
            "SELECT * FROM credit_applications WHERE case_id=? AND company_id=? LIMIT 1",
            (case_id, company_id),
        ).fetchone()
        loan = connection.execute(
            """SELECT COALESCE(SUM(outstanding_amount),0) outstanding,
            COALESCE(MAX(delinquency_days),0) max_delinquency FROM loans WHERE company_id=?""",
            (company_id,),
        ).fetchone()
        customers = connection.execute(
            """SELECT COALESCE(SUM(order_backlog),0) backlog,COALESCE(SUM(revenue_share),0) top3_share,
            COALESCE(MAX(revenue_share),0) largest_share FROM customer_portfolio WHERE company_id=?""",
            (company_id,),
        ).fetchone()
        collateral = connection.execute(
            "SELECT COALESCE(SUM(eligible_value),0) eligible FROM collateral WHERE company_id=?",
            (company_id,),
        ).fetchone()
        assessment = connection.execute(
            "SELECT * FROM credit_assessments WHERE company_id=? ORDER BY assessment_date DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        plan = connection.execute(
            "SELECT * FROM business_plans WHERE company_id=? ORDER BY plan_year DESC LIMIT 1",
            (company_id,),
        ).fetchone()
    if not financials or not application:
        return {"text": "", "sources": []}
    latest = financials[0]
    previous = financials[1] if len(financials) > 1 else latest
    growth = (latest["revenue"] / previous["revenue"] - 1) * 100 if previous["revenue"] else 0
    margin = latest["operating_profit"] / latest["revenue"] * 100 if latest["revenue"] else 0
    current_ratio = latest["current_assets"] / latest["current_liabilities"] * 100 if latest["current_liabilities"] else 0
    overdue = "연체 이력 없이 정상" if loan["max_delinquency"] == 0 else f"최대 {loan['max_delinquency']}일 연체"
    text = f"""## 사업 및 거래 현황
{company['name']}은 {company['industry']} 기업으로 {company['region']} 소재, 임직원 {company['employee_count']}명 규모입니다. {latest['fiscal_year']}년 매출액은 {_won(latest['revenue'])}으로 전년 대비 {growth:.1f}% 증가했습니다. 주요 3개 고객 매출 비중은 {customers['top3_share']:.1f}%, 최대 고객 비중은 {customers['largest_share']:.1f}%이며, 확인된 수주잔고는 {_won(customers['backlog'])}입니다.

## 재무 및 상환능력 분석
{latest['fiscal_year']}년 영업이익은 {_won(latest['operating_profit'])}, 영업이익률은 {margin:.1f}%이며 영업현금흐름은 {_won(latest['cash_flow'])}입니다. 부채비율은 {latest['debt_ratio']:.1f}%, 유동비율은 {current_ratio:.1f}%, 이자보상배율은 {latest['interest_coverage']:.1f}배, DSCR은 {latest['dscr']:.2f}배로 산출됩니다. 기존 대출잔액은 {_won(loan['outstanding'])}이며 {overdue} 상태입니다.

## 자금용도 및 상환계획
신청금액은 {_won(application['requested_amount'])}으로 시설자금 {_won(application['facility_amount'])}, 운전자금 {_won(application['working_capital_amount'])}입니다. 자금용도는 {application['purpose']}이며, {application['term_months']}개월 동안 {application['repayment_method']} 조건입니다. 사업계획상 상환재원은 {plan['repayment_source']}이고 {plan['plan_year']}년 예상 매출액은 {_won(plan['projected_revenue'])}, 예상 영업현금흐름은 {_won(plan['projected_cash_flow'])}입니다.

## 주요 위험요인 및 보완사항
내부신용등급은 {assessment['grade']}, 전망은 {assessment['outlook']}입니다. 주요 위험은 {assessment['watch_reason']}이며, 최대 고객 비중과 수주잔고의 실제 매출 전환 여부를 정기적으로 확인할 필요가 있습니다. 담보 인정가액 합계는 {_won(collateral['eligible'])}으로 담보여력과 현금흐름을 함께 관리하는 조건이 적절합니다.

## 종합 심사의견
최근 매출과 수익성 개선, DSCR {latest['dscr']:.2f}배, 연체 없는 기존 여신, {_won(customers['backlog'])}의 수주잔고를 고려하면 신청 여신은 검토 가능한 수준입니다. 다만 고객사 집중도와 전기차 수요 변동을 감안해 수주 실적, 영업현금흐름 및 설비투자 집행률을 분기별로 점검하는 조건이 필요합니다."""
    return {
        "text": text,
        "sources": [
            "companies", "financials", "loans", "credit_applications",
            "customer_portfolio", "collateral", "credit_assessments", "business_plans",
        ],
    }
