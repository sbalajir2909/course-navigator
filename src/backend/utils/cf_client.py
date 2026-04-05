"""
utils/cf_client.py
Ollama local client — uses llama3.2:latest via http://localhost:11434
Uses asyncio.to_thread so blocking HTTP calls don't stall the event loop.
"""
from __future__ import annotations
import asyncio
import os
import httpx

CF_MODEL_8B  = "llama3.2:latest"
CF_MODEL_70B = "llama3.2:latest"

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Persistent client — avoids re-creating TCP connections on every call
_http_client = httpx.Client(timeout=120.0)


class _Message:
    def __init__(self, content: str):
        self.content = content

class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)

class _Response:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]


def _post_sync(payload: dict) -> str:
    """Synchronous Ollama call — run via asyncio.to_thread to avoid blocking."""
    resp = _http_client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


class _Completions:
    def create(self, model: str, messages: list, temperature: float = 0.7,
               max_tokens: int = 1000, response_format: dict | None = None, **kwargs) -> _Response:
        """Synchronous call — only use from non-async contexts."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"
        content = _post_sync(payload)
        return _Response(content)

    async def acreate(self, model: str, messages: list, temperature: float = 0.7,
                      max_tokens: int = 1000, response_format: dict | None = None, **kwargs) -> _Response:
        """Async version — use this from async code paths."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"

        content = await asyncio.to_thread(_post_sync, payload)
        return _Response(content)


class _Chat:
    def __init__(self):
        self.completions = _Completions()


class CFClient:
    def __init__(self):
        self.chat = _Chat()


def get_cf_client() -> CFClient:
    return CFClient()


get_cf_async_client = get_cf_client
