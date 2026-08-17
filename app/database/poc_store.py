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
    case_id TEXT,
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
    case_id TEXT,
    knowledge_scope TEXT NOT NULL DEFAULT 'case',
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_chunk_metadata (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    case_id TEXT,
    filename TEXT NOT NULL,
    page INTEGER,
    section TEXT,
    chunk_index INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content_hash TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks USING fts5(
    document_id UNINDEXED,
    title,
    content,
    source_path UNINDEXED,
    tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS review_cases (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company_name TEXT NOT NULL,
    review_type TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES review_cases(id),
    conversation_id TEXT,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_access (
    principal_id TEXT NOT NULL,
    case_id TEXT NOT NULL REFERENCES review_cases(id),
    role TEXT NOT NULL DEFAULT 'reviewer',
    PRIMARY KEY(principal_id, case_id)
);
"""


def initialize_database(seed: bool = True) -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        _ensure_column(connection, "conversations", "case_id", "TEXT")
        _ensure_column(connection, "uploaded_files", "case_id", "TEXT")
        _ensure_column(connection, "uploaded_files", "status", "TEXT NOT NULL DEFAULT 'READY'")
        _ensure_column(connection, "uploaded_files", "error_message", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "documents", "case_id", "TEXT")
        _ensure_column(connection, "documents", "knowledge_scope", "TEXT NOT NULL DEFAULT 'case'")
        _ensure_column(connection, "documents", "status", "TEXT NOT NULL DEFAULT 'READY'")
        _ensure_column(connection, "documents", "version", "INTEGER NOT NULL DEFAULT 1")
        connection.execute(
            """INSERT OR IGNORE INTO case_access(principal_id,case_id,role)
            SELECT 'poc-user',id,'owner' FROM review_cases"""
        )
        count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if seed and count == 0:
            _seed_financial_data(connection)


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_case(title: str, company_name: str, review_type: str = "정기심사", owner_name: str = "김심사") -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    case_id = f"CASE-{datetime.now(UTC):%Y}-{uuid.uuid4().hex[:6].upper()}"
    with connect() as connection:
        connection.execute(
            "INSERT INTO review_cases VALUES (?,?,?,?,?,?,?,?,NULL)",
            (case_id, title, company_name, review_type, owner_name, "IN_PROGRESS", now, now),
        )
        connection.execute(
            "INSERT OR IGNORE INTO case_access(principal_id,case_id,role) VALUES ('poc-user',?,'owner')",
            (case_id,),
        )
    return get_case(case_id) or {}


def get_case(case_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """SELECT c.*,(SELECT COUNT(*) FROM uploaded_files f WHERE f.case_id=c.id) document_count
            FROM review_cases c WHERE c.id=?""", (case_id,)
        ).fetchone()
    return dict(row) if row else None


def list_cases(status: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("c.status=?")
        params.append(status)
    if query:
        clauses.append("(c.title LIKE ? OR c.company_name LIKE ? OR c.id LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as connection:
        rows = connection.execute(
            f"""SELECT c.*,(SELECT COUNT(*) FROM uploaded_files f WHERE f.case_id=c.id) document_count
            FROM review_cases c{where} ORDER BY c.updated_at DESC""", params
        ).fetchall()
    return [dict(row) for row in rows]


def update_case_status(case_id: str, status: str) -> dict[str, Any] | None:
    now = datetime.now(UTC).isoformat()
    with connect() as connection:
        connection.execute(
            "UPDATE review_cases SET status=?,updated_at=?,completed_at=? WHERE id=?",
            (status, now, now if status == "COMPLETED" else None, case_id),
        )
    return get_case(case_id)


def ensure_default_case() -> str:
    with connect() as connection:
        row = connection.execute("SELECT id FROM review_cases ORDER BY created_at LIMIT 1").fetchone()
    return str(row[0]) if row else create_case("A기업 / 2026 정기심사", "A기업")["id"]

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


def ensure_conversation(conversation_id: str | None = None, case_id: str | None = None) -> str:
    conversation_id = conversation_id or uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO conversations(id,case_id,created_at,updated_at) VALUES (?,?,?,?)",
            (conversation_id, case_id, now, now),
        )
        if case_id:
            connection.execute("UPDATE conversations SET case_id=? WHERE id=?", (case_id, conversation_id))
    return conversation_id

def save_message(conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
    now = datetime.now(UTC).isoformat()
    with connect() as connection:
        connection.execute(
            "INSERT INTO messages(conversation_id,role,content,metadata_json,created_at) VALUES (?,?,?,?,?)",
            (conversation_id, role, content, json.dumps(metadata or {}, ensure_ascii=False), now),
        )
        connection.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))


def save_uploaded_file(
    conversation_id: str,
    filename: str,
    path: Path,
    mime_type: str,
    size: int,
    text: str,
    case_id: str | None = None,
    status: str = "READY",
) -> str:
    file_id = uuid.uuid4().hex
    with connect() as connection:
        connection.execute(
            """INSERT INTO uploaded_files
            (id,conversation_id,original_name,stored_path,mime_type,size_bytes,extracted_text,created_at,case_id,status,error_message)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (file_id, conversation_id, filename, str(path), mime_type, size, text, datetime.now(UTC).isoformat(), case_id, status, ""),
        )
    return file_id


def update_uploaded_file(
    file_id: str,
    *,
    status: str,
    extracted_text: str | None = None,
    error_message: str = "",
) -> None:
    assignments = ["status=?", "error_message=?"]
    params: list[Any] = [status, error_message[:2_000]]
    if extracted_text is not None:
        assignments.append("extracted_text=?")
        params.append(extracted_text)
    params.append(file_id)
    with connect() as connection:
        connection.execute(f"UPDATE uploaded_files SET {','.join(assignments)} WHERE id=?", params)


def list_case_documents(case_id: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """SELECT id,original_name,mime_type,size_bytes,status,error_message,created_at
            FROM uploaded_files WHERE case_id=? ORDER BY created_at DESC""", (case_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def delete_case_document(case_id: str, document_id: str) -> Path | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT stored_path FROM uploaded_files WHERE id=? AND case_id=?", (document_id, case_id)
        ).fetchone()
        if not row:
            return None
        connection.execute("DELETE FROM document_chunks WHERE document_id=?", (document_id,))
        connection.execute("DELETE FROM document_chunk_metadata WHERE document_id=?", (document_id,))
        connection.execute("DELETE FROM documents WHERE id=?", (document_id,))
        connection.execute("DELETE FROM uploaded_files WHERE id=?", (document_id,))
    return Path(row[0])


def record_agent_event(
    case_id: str,
    conversation_id: str | None,
    agent: str,
    event_type: str,
    content: str = "",
    sources: list[str] | None = None,
) -> None:
    with connect() as connection:
        connection.execute(
            """INSERT INTO agent_events(case_id,conversation_id,agent,event_type,content,sources_json,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (case_id, conversation_id, agent, event_type, content, json.dumps(sources or [], ensure_ascii=False), datetime.now(UTC).isoformat()),
        )


def list_agent_events(case_id: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
    query: str = "SELECT * FROM agent_events WHERE case_id=?"
    params: list[Any] = [case_id]
    if conversation_id:
        query += " AND conversation_id=?"
        params.append(conversation_id)
    with connect() as connection:
        rows = connection.execute(query + " ORDER BY id", params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["sources"] = json.loads(item.pop("sources_json"))
        result.append(item)
    return result

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


def index_document(
    document_id: str,
    title: str,
    source_path: Path,
    mime_type: str,
    text: str,
    case_id: str | None = None,
    knowledge_scope: str = "case",
) -> int:
    chunks = _chunk_text(text)
    now = datetime.now(UTC).isoformat()
    with connect() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO documents
            (id,case_id,knowledge_scope,title,source_path,mime_type,created_at) VALUES (?,?,?,?,?,?,?)""",
            (document_id, case_id, knowledge_scope, title, str(source_path), mime_type, now),
        )
        connection.execute("DELETE FROM document_chunks WHERE document_id=?", (document_id,))
        connection.execute("DELETE FROM document_chunk_metadata WHERE document_id=?", (document_id,))
        connection.executemany(
            "INSERT INTO document_chunks(document_id,title,content,source_path) VALUES (?,?,?,?)",
            [(document_id, title, chunk, str(source_path)) for chunk in chunks],
        )
        connection.executemany(
            """INSERT INTO document_chunk_metadata
            (chunk_id,document_id,case_id,filename,page,section,chunk_index,source_type,version,content_hash)
            VALUES (?,?,?,?,NULL,NULL,?,?,1,?)""",
            [
                (
                    f"{document_id}:{index}", document_id, case_id, title, index,
                    "policy" if knowledge_scope == "common" else "case_document",
                    __import__("hashlib").sha256(chunk.encode()).hexdigest(),
                )
                for index, chunk in enumerate(chunks)
            ],
        )
    return len(chunks)


def search_documents(question: str, limit: int | None = None, case_id: str | None = None) -> list[dict[str, Any]]:
    tokens = [token for token in re.findall(r"[0-9A-Za-z가-힣]+", question) if len(token) >= 2]
    if not tokens:
        return []
    query = " OR ".join(f'"{token}"' for token in tokens[:10])
    with connect() as connection:
        rows = connection.execute(
            """SELECT ch.document_id,ch.title,ch.content,ch.source_path,bm25(document_chunks) score,
            d.case_id,d.knowledge_scope,printf('%s:%d',ch.document_id,ch.rowid) chunk_id,
            NULL chunk_index,NULL page,NULL section,d.version
            FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
            WHERE document_chunks MATCH ? AND d.status='READY'
            AND (? IS NULL OR d.knowledge_scope='common' OR d.case_id=?)
            ORDER BY score LIMIT ?""",
            (query, case_id, case_id, limit or settings.RAG_TOP_K),
        ).fetchall()
    return [dict(row) for row in rows]

def _chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    return [cleaned[start : start + size] for start in range(0, len(cleaned), max(1, size - overlap))]
