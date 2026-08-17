"""Resilient OpenAI-compatible client for the Colab vLLM server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings


class LLMProtocolError(RuntimeError):
    """The upstream response did not follow the OpenAI-compatible contract."""


class ColabLLMClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    def _request(self, messages: list[dict[str, Any]], max_tokens: int, stream: bool = False) -> tuple[str, dict[str, str], dict[str, Any]]:
        return (
            f"{settings.COLAB_LLM_BASE_URL.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {settings.COLAB_LLM_API_KEY}", "Content-Type": "application/json"},
            {"model": settings.COLAB_LLM_MODEL, "messages": messages, "temperature": 0.1, "top_p": 0.8, "max_tokens": max_tokens, "stream": stream},
        )

    async def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(settings.COLAB_LLM_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.COLAB_LLM_TIMEOUT_SECONDS, transport=self.transport) as client:
                    response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code == 429 or exc.response.status_code >= 500
                if not retryable or attempt >= settings.COLAB_LLM_MAX_RETRIES:
                    raise
                await asyncio.sleep(settings.COLAB_LLM_RETRY_BACKOFF_SECONDS * (2**attempt))
        raise RuntimeError("unreachable") from last_error

    async def complete(self, messages: list[dict[str, Any]], max_tokens: int = 1024) -> str:
        url, headers, payload = self._request(messages, max_tokens)
        response = await self._post(url, headers, payload)
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMProtocolError("missing choices[0].message.content") from exc
        if not isinstance(content, str):
            raise LLMProtocolError("message content must be text")
        return content

    async def stream(self, messages: list[dict[str, Any]], max_tokens: int = 1024) -> AsyncIterator[str]:
        url, headers, payload = self._request(messages, max_tokens, stream=True)
        async with httpx.AsyncClient(timeout=settings.COLAB_LLM_TIMEOUT_SECONDS, transport=self.transport) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        event = json.loads(data)
                        content = event["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                        raise LLMProtocolError("malformed streaming event") from exc
                    if content is not None and not isinstance(content, str):
                        raise LLMProtocolError("stream content must be text")
                    if content:
                        yield content
