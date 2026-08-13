"""OpenAI-compatible multimodal client for the Colab vLLM server."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings


class ColabLLMClient:
    """Small async client that keeps the Colab API key on the server."""

    async def complete(self, messages: list[dict[str, Any]], max_tokens: int = 1024) -> str:
        url = f"{settings.COLAB_LLM_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.COLAB_LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.COLAB_LLM_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "top_p": 0.8,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=settings.COLAB_LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def stream(self, messages: list[dict[str, Any]], max_tokens: int = 1024) -> AsyncIterator[str]:
        url = f"{settings.COLAB_LLM_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.COLAB_LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.COLAB_LLM_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "top_p": 0.8,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=settings.COLAB_LLM_TIMEOUT_SECONDS) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    content = json.loads(data)["choices"][0]["delta"].get("content")
                    if content:
                        yield content
