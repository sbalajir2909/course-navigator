"""
api/cf_client.py
Cloudflare Workers AI client — exhausts ALL available CF models before falling back to OpenAI.

Model chains (tried in order until one succeeds):
  teach    → llama-3.3-70b-fp8-fast → qwq-32b → deepseek-r1-70b → deepseek-r1-7b
             → llama-3.1-70b → llama-3.1-8b → mistral-7b-v0.2 → gemma-7b
  validate → same chain (strict JSON grading needs a capable model first)
  course   → llama-3.1-70b → qwq-32b → deepseek-r1-70b → llama-3.3-70b-fp8-fast
             → deepseek-r1-7b → llama-3.1-8b → mistral-7b-v0.2 → gemma-7b

Each model is tried with the same payload. On 429 (neuron quota) or any other CF error,
the next model in the chain is tried immediately. OpenAI is only used if every CF model fails.
"""
from __future__ import annotations
import json
import os
import re
from typing import AsyncGenerator

import httpx

# ── Model chains (exhausted in order before OpenAI fallback) ──────────────────
_CF_CHAIN_TEACH = [
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "@cf/qwen/qwq-32b",
    "@cf/deepseek-ai/deepseek-r1-distill-llama-70b",
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-7b",
    "@cf/meta/llama-3.1-70b-instruct",
    "@cf/meta/llama-3.1-8b-instruct",
    "@cf/mistral/mistral-7b-instruct-v0.2",
    "@cf/google/gemma-7b-it",
]

_CF_CHAIN_COURSE = [
    "@cf/meta/llama-3.1-70b-instruct",
    "@cf/qwen/qwq-32b",
    "@cf/deepseek-ai/deepseek-r1-distill-llama-70b",
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-7b",
    "@cf/meta/llama-3.1-8b-instruct",
    "@cf/mistral/mistral-7b-instruct-v0.2",
    "@cf/google/gemma-7b-it",
]

CF_CHAINS: dict[str, list[str]] = {
    "teach":    _CF_CHAIN_TEACH,
    "validate": _CF_CHAIN_TEACH,   # same quality requirement as teach
    "course":   _CF_CHAIN_COURSE,
}

# OpenAI fallback — only reached when every CF model in the chain fails
OAI_FALLBACK = {
    "teach":    "gpt-4o-mini",
    "validate": "gpt-4o",
    "course":   "gpt-4o-mini",
}

# Legacy single-model map kept for embed
CF_MODELS = {
    "embed": "@cf/baai/bge-m3",
}


def _cf_url(model: str) -> str:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"


def _cf_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('CLOUDFLARE_API_TOKEN', '')}",
        "Content-Type": "application/json",
    }


def _extract_json(text: str) -> dict | list:
    """Parse JSON from LLM response text, handling markdown code fences."""
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


def _parse_cf_response(data: dict) -> str:
    """Extract the text from a Cloudflare AI response dict."""
    if not data.get("success", True):
        errors = data.get("errors", [])
        raise RuntimeError(f"CF API error: {errors}")
    result = data.get("result", {})
    response = result.get("response") or result.get("generated_text")
    if response is None:
        raise RuntimeError(f"Empty response from CF. Full result: {result}")
    if isinstance(response, str):
        return response.strip()
    return str(response)


async def _try_cf_chain(
    model_key: str,
    payload: dict,
) -> str | None:
    """
    Try every model in the chain for model_key.
    Returns the response text from the first model that succeeds, or None if all fail.
    """
    chain = CF_CHAINS.get(model_key, _CF_CHAIN_TEACH)
    headers = _cf_headers()

    for model in chain:
        url = _cf_url(model)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if not resp.is_success:
                    body = resp.text[:300]
                    print(f"[CF_CLIENT] {model} failed ({resp.status_code}): {body[:120]} — trying next")
                    continue
                text = _parse_cf_response(resp.json())
                print(f"[CF_CLIENT] {model} succeeded for '{model_key}'")
                return text
        except Exception as e:
            print(f"[CF_CLIENT] {model} error: {e} — trying next")
            continue

    return None  # all CF models failed


# ── Non-streaming text completion ─────────────────────────────────────────────

async def complete(
    messages: list[dict],
    model_key: str = "teach",
    max_tokens: int = 300,
    temperature: float = 0.4,
) -> str:
    """
    Non-streaming text completion.
    Exhausts the full CF model chain before falling back to OpenAI.
    """
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    text = await _try_cf_chain(model_key, payload)
    if text is not None:
        return text

    print(f"[CF_CLIENT] All CF models exhausted for '{model_key}' — falling back to OpenAI")
    return await _oai_complete(messages, model_key, max_tokens, temperature)


# ── JSON completion ───────────────────────────────────────────────────────────

async def complete_json(
    messages: list[dict],
    model_key: str = "course",
    max_tokens: int = 1000,
    temperature: float = 0.3,
) -> dict | list:
    """
    Completion parsed as JSON.
    Exhausts the full CF model chain before falling back to OpenAI json_mode.
    """
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    cf_text = await _try_cf_chain(model_key, payload)

    if cf_text is not None:
        if isinstance(cf_text, dict):
            return cf_text
        try:
            return _extract_json(cf_text)
        except (ValueError, json.JSONDecodeError) as parse_err:
            print(f"[CF_CLIENT] JSON parse failed: {parse_err} — falling back to OpenAI (json_mode)")

    print(f"[CF_CLIENT] All CF models exhausted for '{model_key}' — falling back to OpenAI (json_mode)")
    oai_text = await _oai_complete(messages, model_key, max_tokens, temperature, json_mode=True)
    return _extract_json(oai_text)


# ── Streaming text completion ─────────────────────────────────────────────────

async def stream_text(
    messages: list[dict],
    model_key: str = "teach",
    max_tokens: int = 500,
    temperature: float = 0.4,
) -> AsyncGenerator[str, None]:
    """
    Streaming completion — yields text tokens as they arrive via SSE.
    Tries each CF model in the chain; falls back to a full non-streaming call if all fail.
    """
    chain = CF_CHAINS.get(model_key, _CF_CHAIN_TEACH)
    headers = _cf_headers()
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    for model in chain:
        url = _cf_url(model)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if not resp.is_success:
                        body = await resp.aread()
                        print(f"[CF_CLIENT] stream {model} failed ({resp.status_code}) — trying next")
                        continue
                    tokens_yielded = 0
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[6:].strip()
                        if chunk == "[DONE]":
                            return
                        try:
                            data = json.loads(chunk)
                            token = data.get("response", "")
                            if token:
                                yield token
                                tokens_yielded += 1
                        except json.JSONDecodeError:
                            continue
                    if tokens_yielded > 0:
                        return  # successful stream
        except Exception as e:
            print(f"[CF_CLIENT] stream {model} error: {e} — trying next")
            continue

    # All CF streaming failed — fall back to full non-streaming response
    print(f"[CF_CLIENT] All CF stream models failed — falling back to non-streaming OpenAI")
    text = await _oai_complete(messages, model_key, max_tokens, temperature)
    yield text


# ── Embeddings ────────────────────────────────────────────────────────────────

async def embed(text: str) -> list[float]:
    """Generate embedding using @cf/baai/bge-m3. Returns a float vector."""
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CF_MODELS['embed']}"
    payload = {"text": [text]}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=_cf_headers(), json=payload)
        resp.raise_for_status()
        data = resp.json()

    result = data.get("result", {})
    vectors = result.get("data", [[]])
    return vectors[0] if vectors else []


# ── OpenAI fallback ───────────────────────────────────────────────────────────

async def _oai_complete(
    messages: list[dict],
    model_key: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool = False,
) -> str:
    """OpenAI fallback — used only when every Cloudflare model in the chain has failed."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    oai_model = OAI_FALLBACK.get(model_key, "gpt-4o-mini")

    kwargs: dict = dict(
        model=oai_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    print(f"[CF_CLIENT] OpenAI fallback: {oai_model} for '{model_key}'")
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content.strip()
