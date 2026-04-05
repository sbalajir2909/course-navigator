"""
api/cf_client.py
Unified LLM client using Ollama via OpenAI-compatible API.

Provider order:
  1. Ollama  → AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
  2. OpenAI  → gpt-4o (validate) / gpt-4o-mini (everything else)

All JSON calls strip response_format — instead the JSON instruction is
injected into the system prompt so every model (including ones that don't
support response_format) returns clean JSON.
"""
from __future__ import annotations
import json
import os
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI

from api.config.models import (
    OLLAMA_BASE_URL,
    TEACH_MODEL, VALIDATE_MODEL, COURSE_MODEL, EMBED_MODEL,
    OAI_VALIDATE_MODEL, OAI_DEFAULT_MODEL,
)

OLLAMA_MODELS: dict[str, str] = {
    "teach":    TEACH_MODEL,
    "validate": VALIDATE_MODEL,
    "course":   COURSE_MODEL,
}
OAI_FALLBACK: dict[str, str] = {
    "teach":    OAI_DEFAULT_MODEL,
    "validate": OAI_VALIDATE_MODEL,
    "course":   OAI_DEFAULT_MODEL,
}

_JSON_INSTRUCTION = (
    "Respond only with valid JSON. "
    "No markdown, no code blocks, no explanation outside the JSON."
)


# ── Client factories ──────────────────────────────────────────────────────────

def _ollama() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | list:
    """Parse JSON from model output, tolerating markdown fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"No JSON found in response: {text[:300]}")


def _with_json_instruction(messages: list[dict]) -> list[dict]:
    """
    Inject the JSON instruction into the system message.
    If no system message exists, prepend one.
    """
    msgs = list(messages)
    if msgs and msgs[0].get("role") == "system":
        msgs[0] = {**msgs[0], "content": msgs[0]["content"].rstrip() + "\n\n" + _JSON_INSTRUCTION}
    else:
        msgs.insert(0, {"role": "system", "content": _JSON_INSTRUCTION})
    return msgs


# ── Public API ────────────────────────────────────────────────────────────────

async def complete(
    messages: list[dict],
    model_key: str = "teach",
    max_tokens: int = 500,
    temperature: float = 0.4,
) -> str:
    """Non-streaming text completion. Ollama → OpenAI fallback."""
    model = OLLAMA_MODELS.get(model_key, TEACH_MODEL)

    # 1. Ollama
    try:
        resp = await _ollama().chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content.strip()
        print(f"[OLLAMA] {model} ✓ ('{model_key}')")
        return text
    except Exception as e:
        print(f"[OLLAMA] {model} failed ('{model_key}'): {e} — trying OpenAI")

    # 2. OpenAI
    oai_model = OAI_FALLBACK.get(model_key, OAI_DEFAULT_MODEL)
    resp = await _openai().chat.completions.create(
        model=oai_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    print(f"[OAI] {oai_model} ✓ ('{model_key}')")
    return resp.choices[0].message.content.strip()


async def complete_json(
    messages: list[dict],
    model_key: str = "course",
    max_tokens: int = 1000,
    temperature: float = 0.3,
) -> dict | list:
    """
    JSON completion. Injects JSON instruction into system prompt.
    No response_format — not all Ollama models support it.
    Falls back to OpenAI json_mode if Ollama fails.
    """
    msgs = _with_json_instruction(messages)
    model = OLLAMA_MODELS.get(model_key, COURSE_MODEL)

    # 1. Ollama (no response_format)
    try:
        resp = await _ollama().chat.completions.create(
            model=model,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content.strip()
        result = _extract_json(text)
        print(f"[OLLAMA] {model} ✓ JSON ('{model_key}')")
        return result
    except Exception as e:
        print(f"[OLLAMA] {model} failed JSON ('{model_key}'): {e} — trying OpenAI")

    # 2. OpenAI with json_mode
    oai_model = OAI_FALLBACK.get(model_key, OAI_DEFAULT_MODEL)
    resp = await _openai().chat.completions.create(
        model=oai_model,
        messages=msgs,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    print(f"[OAI] {oai_model} ✓ JSON ('{model_key}')")
    return _extract_json(resp.choices[0].message.content.strip())


async def stream_text(
    messages: list[dict],
    model_key: str = "teach",
    max_tokens: int = 500,
    temperature: float = 0.4,
) -> AsyncGenerator[str, None]:
    """Streaming completion. Tries Ollama first; falls back to non-streaming OpenAI."""
    model = OLLAMA_MODELS.get(model_key, TEACH_MODEL)

    # 1. Ollama streaming
    try:
        stream = await _ollama().chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        tokens_seen = 0
        async for chunk in stream:
            token = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if token:
                yield token
                tokens_seen += 1
        if tokens_seen > 0:
            return
        raise RuntimeError("Empty stream from Ollama")
    except Exception as e:
        print(f"[OLLAMA] stream failed ('{model_key}'): {e} — falling back to OpenAI")

    # 2. OpenAI non-streaming fallback
    text = await complete(messages, model_key=model_key, max_tokens=max_tokens, temperature=temperature)
    yield text


async def embed(text: str) -> list[float]:
    """Generate embedding using bge-m3 via Ollama. Returns [] on failure."""
    try:
        resp = await _ollama().embeddings.create(model=EMBED_MODEL, input=text)
        return resp.data[0].embedding
    except Exception as e:
        print(f"[OLLAMA] embed failed: {e}")
        return []
