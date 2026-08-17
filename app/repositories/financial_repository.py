"""Allow-listed structured financial access; the only DB path used by query services."""

from __future__ import annotations

from typing import Any

from app.database.poc_store import connect


class FinancialRepository:
    ALLOWED_METRICS = {
        "revenue", "operating_profit", "net_income", "total_assets",
        "total_liabilities", "equity", "cash_flow", "debt_ratio", "interest_coverage",
    }

    def company_names(self) -> list[str]:
        with connect() as connection:
            return [str(row[0]) for row in connection.execute("SELECT name FROM companies")]

    def company_financials(self, company: str, years: int = 4) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """SELECT c.name,c.industry,c.credit_grade,c.risk_level,f.*
                FROM companies c JOIN financials f ON f.company_id=c.id
                WHERE c.name=? ORDER BY f.fiscal_year DESC LIMIT ?""",
                (company, years),
            ).fetchall()
        return [dict(row) for row in rows]

    def delinquent_loans(self, limit: int) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """SELECT c.name,c.credit_grade,c.risk_level,l.product,l.outstanding_amount,l.delinquency_days
                FROM loans l JOIN companies c ON c.id=l.company_id
                WHERE l.delinquency_days>0 ORDER BY l.delinquency_days DESC LIMIT ?""", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def high_risk_companies(self, year: int, limit: int) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """SELECT c.name,c.industry,c.credit_grade,c.risk_level,f.revenue,f.debt_ratio,f.interest_coverage
                FROM companies c JOIN financials f ON f.company_id=c.id
                WHERE f.fiscal_year=? AND (c.risk_level='고위험' OR f.debt_ratio>=250)
                ORDER BY f.debt_ratio DESC LIMIT ?""", (year, limit)
            ).fetchall()
        return [dict(row) for row in rows]

