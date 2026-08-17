"""Deterministic intent-to-query service for common financial questions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.config import settings
from app.repositories.financial_repository import FinancialRepository


class QueryIntentType(StrEnum):
    COMPANY_FINANCIALS = "company_financials"
    DELINQUENCY = "delinquency"
    HIGH_RISK = "high_risk"


@dataclass(slots=True)
class QueryIntent:
    type: QueryIntentType
    company: str | None = None
    year: int = 2025


@dataclass(slots=True)
class QueryResult:
    intent: QueryIntent
    query_id: str
    rows: list[dict[str, Any]]

    @property
    def sql(self) -> str:
        return self.query_id

    def as_context(self) -> str:
        return json.dumps({"query_id": self.query_id, "intent": self.intent.type, "rows": self.rows}, ensure_ascii=False)


class FinancialQueryService:
    def __init__(self, repository: FinancialRepository | None = None) -> None:
        self.repository = repository or FinancialRepository()

    def extract_intent(self, question: str) -> QueryIntent | None:
        company = next((name for name in self.repository.company_names() if name in question), None)
        if company:
            return QueryIntent(QueryIntentType.COMPANY_FINANCIALS, company=company)
        if any(token in question for token in ("연체", "부실")):
            return QueryIntent(QueryIntentType.DELINQUENCY)
        if any(token in question for token in ("고위험", "위험 기업", "부채비율 높은")):
            return QueryIntent(QueryIntentType.HIGH_RISK)
        return None

    def execute(self, question: str) -> QueryResult | None:
        intent = self.extract_intent(question)
        if not intent:
            return None
        limit = max(1, min(settings.SQL_MAX_ROWS, 100))
        if intent.type == QueryIntentType.COMPANY_FINANCIALS:
            rows = self.repository.company_financials(intent.company or "", min(limit, 4))
        elif intent.type == QueryIntentType.DELINQUENCY:
            rows = self.repository.delinquent_loans(limit)
        else:
            rows = self.repository.high_risk_companies(intent.year, limit)
        return QueryResult(intent, f"predefined:{intent.type}", rows[:limit])

