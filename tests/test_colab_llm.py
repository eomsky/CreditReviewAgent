import asyncio
import json

import httpx

from app.clients.colab_llm import ColabLLMClient


def test_complete_records_finish_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "완성된 답변"}, "finish_reason": "stop"}]},
        )

    client = ColabLLMClient(httpx.MockTransport(handler))
    answer = asyncio.run(client.complete([{"role": "user", "content": "질문"}], max_tokens=400))
    assert answer == "완성된 답변"
    assert client.last_finish_reason == "stop"


def test_stream_records_length_finish_reason():
    events = [
        {"choices": [{"delta": {"content": "중간 "}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
    ]
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = ColabLLMClient(httpx.MockTransport(handler))

    async def collect():
        return [token async for token in client.stream([{"role": "user", "content": "질문"}], max_tokens=300)]

    assert asyncio.run(collect()) == ["중간 "]
    assert client.last_finish_reason == "length"
