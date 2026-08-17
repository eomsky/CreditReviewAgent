from pathlib import Path
import asyncio

import pytest

from app.clients.colab_llm import ColabLLMClient
from app.core.config import settings
from app.database.poc_store import initialize_database
from app.graphs.qa_graph import run_qa


def test_generator_answer_is_revised_by_validator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'graph.db'}")
    initialize_database(seed=True)
    responses = iter(
        [
            "근거 없이 모두 안전합니다.",
            '{"approved": false, "issues": ["근거 없는 단정"]}',
            "고위험 기업은 부채비율과 상환재원을 추가 검토해야 합니다.",
            '{"approved": true, "issues": []}',
        ]
    )

    async def fake_complete(self, messages, max_tokens=1024):
        return next(responses)

    monkeypatch.setattr(ColabLLMClient, "complete", fake_complete)
    result = asyncio.run(run_qa("고위험 기업을 알려줘"))
    assert result["approved"] is True
    assert result["revision_count"] == 1
    assert "추가 검토" in result["final_answer"]


def test_stream_qa_yields_tokens_before_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.graphs.qa_graph import stream_qa

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'stream.db'}")
    initialize_database(seed=True)

    async def fake_stream(self, messages, max_tokens=1024):
        yield "첫 "
        yield "답변"

    async def fake_complete(self, messages, max_tokens=1024):
        return '{"approved": true, "issues": []}'

    monkeypatch.setattr(ColabLLMClient, "stream", fake_stream)
    monkeypatch.setattr(ColabLLMClient, "complete", fake_complete)

    async def collect():
        return [event async for event in stream_qa("고위험 기업을 알려줘")]

    events = asyncio.run(collect())
    assert [event["content"] for event in events if event["type"] == "token"] == ["첫 ", "답변"]
    assert events[-1]["type"] == "done"
    assert events[-1]["result"]["approved"] is True
