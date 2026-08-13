"""Persistent SQLite store used by the POC chat, text-to-SQL, and lexical RAG."""

from __future__ import annotations

import json
import random
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT, settings


ALLOWED_QUERY_TABLES = {"companies", "financials", "loans"}


def database_path() -> Path:
    raw = settings.DATABASE_URL.rsplit("///", 1)[-1]
    path = Path(raw)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    industry TEXT NOT NULL,
    region TEXT NOT NULL,
    employee_count INTEGER NOT NULL,
    founded_year INTEGER NOT NULL,
    credit_grade TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS financials (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    fiscal_year INTEGER NOT NULL,
    revenue REAL NOT NULL,
    operating_profit REAL NOT NULL,
    net_income REAL NOT NULL,
    total_assets REAL NOT NULL,
    total_liabilities REAL NOT NULL,
    equity REAL NOT NULL,
    cash_flow REAL NOT NULL,
    debt_ratio REAL NOT NULL,
    interest_coverage REAL NOT NULL,
    UNIQUE(company_id, fiscal_year)
);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    product TEXT NOT NULL,
    approved_amount REAL NOT NULL,
    outstanding_amount REAL NOT NULL,
    interest_rate REAL NOT NULL,
    maturity_date TEXT NOT NULL,
    delinquency_days INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS uploaded_files (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    extracted_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks USING fts5(
    document_id UNINDEXED,
    title,
    content,
    source_path UNINDEXED,
    tokenize='unicode61'
);
"""


def initialize_database(seed: bool = True) -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if seed and count == 0:
            _seed_financial_data(connection)


def _seed_financial_data(connection: sqlite3.Connection, company_count: int = 180) -> None:
    rng = random.Random(20260814)
    industries = ["제조", "건설", "도소매", "IT서비스", "운수", "바이오", "식품", "부동산", "에너지"]
    regions = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "충남", "경남"]
    prefixes = ["대한", "한빛", "미래", "세종", "청솔", "누리", "해성", "우진", "가온", "동아"]
    suffixes = ["산업", "테크", "물산", "솔루션", "개발", "유통", "건설", "시스템", "에너지"]
    now = datetime.now(UTC).isoformat()

    for company_id in range(1, company_count + 1):
        name = f"{rng.choice(prefixes)}{rng.choice(suffixes)}{company_id:03d}"
        industry = rng.choice(industries)
        risk_roll = rng.random()
        risk = "고위험" if risk_roll < 0.18 else "주의" if risk_roll < 0.43 else "정상"
        grade = rng.choice(["A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB"]) if risk != "고위험" else rng.choice(["BB-", "B+", "B"])
        connection.execute(
            "INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, name, industry, rng.choice(regions), rng.randint(12, 2400), rng.randint(1985, 2021), grade, risk, now),
        )
        base_revenue = rng.uniform(8_000, 850_000)
        debt_bias = rng.uniform(180, 420) if risk == "고위험" else rng.uniform(45, 240)
        for year in range(2022, 2026):
            growth = 1 + rng.uniform(-0.18, 0.25)
            base_revenue *= growth
            margin = rng.uniform(-0.08, 0.16) if risk == "고위험" else rng.uniform(0.015, 0.2)
            operating_profit = base_revenue * margin
            net_income = operating_profit * rng.uniform(0.45, 0.9) - rng.uniform(0, base_revenue * 0.025)
            assets = base_revenue * rng.uniform(0.65, 1.8)
            debt_ratio = max(15.0, debt_bias + rng.uniform(-35, 35))
            equity = assets / (1 + debt_ratio / 100)
            liabilities = assets - equity
            coverage = max(-2.0, operating_profit / max(liabilities * rng.uniform(0.025, 0.07), 1))
            connection.execute(
                """INSERT INTO financials
                (company_id,fiscal_year,revenue,operating_profit,net_income,total_assets,total_liabilities,equity,cash_flow,debt_ratio,interest_coverage)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (company_id, year, round(base_revenue, 2), round(operating_profit, 2), round(net_income, 2), round(assets, 2), round(liabilities, 2), round(equity, 2), round(net_income + rng.uniform(-0.04, 0.08) * base_revenue, 2), round(debt_ratio, 2), round(coverage, 2)),
            )
        for _ in range(rng.randint(1, 3)):
            amount = rng.uniform(500, 120_000)
            delinquency = rng.choice([0] * 8 + [5, 15, 32, 65]) if risk != "정상" else rng.choice([0] * 14 + [3])
            connection.execute(
                """INSERT INTO loans
                (company_id,product,approved_amount,outstanding_amount,interest_rate,maturity_date,delinquency_days,status)
                VALUES (?,?,?,?,?,?,?,?)""",
                (company_id, rng.choice(["운전자금", "시설자금", "무역금융", "매출채권담보"]), round(amount, 2), round(amount * rng.uniform(0.25, 0.98), 2), round(rng.uniform(3.2, 9.8), 2), f"{rng.randint(2026, 2031)}-{rng.randint(1,12):02d}-28", delinquency, "연체" if delinquency >= 30 else "정상"),
            )


def ensure_conversation(conversation_id: str | None = None) -> str:
    conversation_id = conversation_id or uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO conversations(id,created_at,updated_at) VALUES (?,?,?)",
            (conversation_id, now, now),
        )
    return conversation_id


def save_message(conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
    now = datetime.now(UTC).isoformat()
    with connect() as connection:
        connection.execute(
            "INSERT INTO messages(conversation_id,role,content,metadata_json,created_at) VALUES (?,?,?,?,?)",
            (conversation_id, role, content, json.dumps(metadata or {}, ensure_ascii=False), now),
        )
        connection.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))


def save_uploaded_file(conversation_id: str, filename: str, path: Path, mime_type: str, size: int, text: str) -> str:
    file_id = uuid.uuid4().hex
    with connect() as connection:
        connection.execute(
            "INSERT INTO uploaded_files VALUES (?,?,?,?,?,?,?,?)",
            (file_id, conversation_id, filename, str(path), mime_type, size, text, datetime.now(UTC).isoformat()),
        )
    return file_id


@dataclass(slots=True)
class SQLQueryResult:
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]

    def as_context(self) -> str:
        return json.dumps({"sql": self.sql, "rows": self.rows}, ensure_ascii=False, default=str)


class TextToSQLService:
    """Converts common Korean credit questions into allow-listed read-only SQL."""

    def translate(self, question: str) -> tuple[str, dict[str, Any]] | None:
        q = question.strip()
        company = self._company_name(q)
        if company:
            if any(token in q for token in ("재무", "매출", "부채", "이익", "현금", "상환")):
                return (
                    """SELECT c.name,c.industry,c.credit_grade,c.risk_level,f.fiscal_year,
                    f.revenue,f.operating_profit,f.net_income,f.debt_ratio,f.interest_coverage,f.cash_flow
                    FROM companies c JOIN financials f ON f.company_id=c.id
                    WHERE c.name=:company ORDER BY f.fiscal_year DESC LIMIT 4""",
                    {"company": company},
                )
            return ("SELECT * FROM companies WHERE name=:company LIMIT 1", {"company": company})
        if any(token in q for token in ("연체", "부실")):
            return (
                """SELECT c.name,c.credit_grade,c.risk_level,l.product,l.outstanding_amount,l.delinquency_days
                FROM loans l JOIN companies c ON c.id=l.company_id
                WHERE l.delinquency_days>0 ORDER BY l.delinquency_days DESC LIMIT 30""",
                {},
            )
        if any(token in q for token in ("고위험", "위험 기업", "부채비율 높은")):
            return (
                """SELECT c.name,c.industry,c.credit_grade,c.risk_level,f.revenue,f.debt_ratio,f.interest_coverage
                FROM companies c JOIN financials f ON f.company_id=c.id
                WHERE f.fiscal_year=2025 AND (c.risk_level='고위험' OR f.debt_ratio>=250)
                ORDER BY f.debt_ratio DESC LIMIT 30""",
                {},
            )
        if any(token in q for token in ("업종", "산업별", "평균")):
            return (
                """SELECT c.industry,COUNT(*) company_count,ROUND(AVG(f.revenue),2) avg_revenue,
                ROUND(AVG(f.debt_ratio),2) avg_debt_ratio,ROUND(AVG(f.interest_coverage),2) avg_interest_coverage
                FROM companies c JOIN financials f ON f.company_id=c.id WHERE f.fiscal_year=2025
                GROUP BY c.industry ORDER BY avg_debt_ratio DESC LIMIT 30""",
                {},
            )
        return None

    def execute(self, question: str) -> SQLQueryResult | None:
        translated = self.translate(question)
        if not translated:
            return None
        sql, params = translated
        self._validate(sql)
        with connect() as connection:
            cursor = connection.execute(sql, params)
            columns = [item[0] for item in cursor.description or []]
            rows = [dict(row) for row in cursor.fetchmany(settings.SQL_MAX_ROWS)]
        return SQLQueryResult(sql=" ".join(sql.split()), columns=columns, rows=rows)

    @staticmethod
    def _company_name(question: str) -> str | None:
        with connect() as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM companies")]
        return next((name for name in names if name in question), None)

    @staticmethod
    def _validate(sql: str) -> None:
        normalized = re.sub(r"\s+", " ", sql.strip().lower())
        if not normalized.startswith("select ") or ";" in normalized:
            raise ValueError("읽기 전용 SELECT만 허용됩니다.")
        referenced = set(re.findall(r"(?:from|join)\s+([a-z_]+)", normalized))
        if not referenced or not referenced.issubset(ALLOWED_QUERY_TABLES):
            raise ValueError("허용되지 않은 테이블입니다.")


def index_document(document_id: str, title: str, source_path: Path, mime_type: str, text: str) -> int:
    chunks = _chunk_text(text)
    now = datetime.now(UTC).isoformat()
    with connect() as connection:
        connection.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?)", (document_id, title, str(source_path), mime_type, now))
        connection.execute("DELETE FROM document_chunks WHERE document_id=?", (document_id,))
        connection.executemany(
            "INSERT INTO document_chunks(document_id,title,content,source_path) VALUES (?,?,?,?)",
            [(document_id, title, chunk, str(source_path)) for chunk in chunks],
        )
    return len(chunks)


def search_documents(question: str, limit: int | None = None) -> list[dict[str, Any]]:
    tokens = [token for token in re.findall(r"[0-9A-Za-z가-힣]+", question) if len(token) >= 2]
    if not tokens:
        return []
    query = " OR ".join(f'"{token}"' for token in tokens[:10])
    with connect() as connection:
        rows = connection.execute(
            """SELECT document_id,title,content,source_path,bm25(document_chunks) score
            FROM document_chunks WHERE document_chunks MATCH ? ORDER BY score LIMIT ?""",
            (query, limit or settings.RAG_TOP_K),
        ).fetchall()
    return [dict(row) for row in rows]


def _chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    return [cleaned[start : start + size] for start in range(0, len(cleaned), max(1, size - overlap))]
