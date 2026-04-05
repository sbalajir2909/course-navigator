"""
api/cf_client.py
Unified LLM client — tries providers in this order:

  1. Ollama local  (http://localhost:11434)  — self-hosted, free, fast
  2. Ollama remote (OLLAMA_REMOTE_URL)       — Gautschi GPU node via SSH tunnel
  3. Cloudflare Workers AI chain             — 8 models before giving up
  4. OpenAI                                  — final fallback (costs money)

Model assignments:
  teach    → llama3.1:8b
  validate → qwen2.5:72b   (strict grading needs the bigger model)
  course   → llama3.1:8b

Set in .env:
  OLLAMA_LOCAL_URL=http://localhost:11434       (default, omit to skip local)
  OLLAMA_REMOTE_URL=http://localhost:11435      (Gautschi tunnel port, omit to skip)
"""
from __future__ import annotations
import json
import os
import re
from typing import AsyncGenerator

import httpx

# ── Ollama model map ──────────────────────────────────────────────────────────
OLLAMA_MODELS: dict[str, str] = {
    "teach":    "llama3.1:8b",
    "validate": "qwen2.5:72b",
    "course":   "llama3.1:8b",
}

# ── Cloudflare model chains (used only if Ollama unavailable) ─────────────────
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
    "validate": _CF_CHAIN_TEACH,
    "course":   _CF_CHAIN_COURSE,
}

# OpenAI — final fallback
OAI_FALLBACK: dict[str, str] = {
    "teach":    "gpt-4o-mini",
    "validate": "gpt-4o",
    "course":   "gpt-4o-mini",
}

# Embed model (CF only — no Ollama needed for embeddings in this project)
CF_MODELS = {"embed": "@cf/baai/bge-m3"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | list:
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
    if not data.get("success", True):
        raise RuntimeError(f"CF API error: {data.get('errors', [])}")
    result = data.get("result", {})
    response = result.get("response") or result.get("generated_text")
    if response is None:
        raise RuntimeError(f"Empty CF result: {result}")
    return response.strip() if isinstance(response, str) else str(response)


def _cf_url(model: str) -> str:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"


def _cf_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('CLOUDFLARE_API_TOKEN', '')}",
        "Content-Type": "application/json",
    }


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _ollama_endpoints() -> list[str]:
    """Return Ollama base URLs to try, in order (local first, then remote)."""
    endpoints: list[str] = []
    local = os.getenv("OLLAMA_LOCAL_URL", "http://localhost:11434").rstrip("/")
    remote = os.getenv("OLLAMA_REMOTE_URL", "").rstrip("/")
    endpoints.append(local)           # always try local first
    if remote:
        endpoints.append(remote)      # Gautschi via SSH tunnel
    return endpoints


async def _try_ollama(
    model_key: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
) -> str | None:
    """
    Try each Ollama endpoint using the OpenAI-compatible /v1/chat/completions API.
    Returns the response text, or None if every endpoint fails.
    """
    model = OLLAMA_MODELS.get(model_key, "llama3.1:8b")
    payload = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
        "stream":      False,
    }

    for base_url in _ollama_endpoints():
        url = f"{base_url}/v1/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                if not resp.is_success:
                    print(f"[OLLAMA] {base_url} → {resp.status_code} — trying next")
                    continue
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                print(f"[OLLAMA] {base_url} ({model}) succeeded for '{model_key}'")
                return text
        except Exception as e:
            print(f"[OLLAMA] {base_url} error: {e} — trying next")
            continue

    return None


async def _try_cf_chain(model_key: str, payload: dict) -> str | None:
    """Try every CF model in the chain. Returns text or None."""
    chain = CF_CHAINS.get(model_key, _CF_CHAIN_TEACH)
    headers = _cf_headers()
    for model in chain:
        url = _cf_url(model)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if not resp.is_success:
                    print(f"[CF] {model} → {resp.status_code} — trying next")
                    continue
                text = _parse_cf_response(resp.json())
                print(f"[CF] {model} succeeded for '{model_key}'")
                return text
        except Exception as e:
            print(f"[CF] {model} error: {e} — trying next")
            continue
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def complete(
    messages: list[dict],
    model_key: str = "teach",
    max_tokens: int = 500,
    temperature: float = 0.4,
) -> str:
    """Non-streaming text completion. Ollama → CF chain → OpenAI."""
    # 1. Ollama (local + remote)
    text = await _try_ollama(model_key, messages, max_tokens, temperature)
    if text is not None:
        return text

    # 2. Cloudflare chain
    cf_payload = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    text = await _try_cf_chain(model_key, cf_payload)
    if text is not None:
        return text

    # 3. OpenAI
    print(f"[CLIENT] All providers failed for '{model_key}' — falling back to OpenAI")
    return await _oai_complete(messages, model_key, max_tokens, temperature)


async def complete_json(
    messages: list[dict],
    model_key: str = "course",
    max_tokens: int = 1000,
    temperature: float = 0.3,
) -> dict | list:
    """JSON completion. Ollama → CF chain → OpenAI json_mode."""
    # 1. Ollama
    text = await _try_ollama(model_key, messages, max_tokens, temperature)
    if text is not None:
        try:
            return _extract_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[OLLAMA] JSON parse failed: {e} — trying CF")

    # 2. CF chain
    cf_payload = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    cf_text = await _try_cf_chain(model_key, cf_payload)
    if cf_text is not None:
        try:
            return _extract_json(cf_text)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[CF] JSON parse failed: {e} — falling back to OpenAI")

    # 3. OpenAI json_mode
    print(f"[CLIENT] All providers failed for '{model_key}' — falling back to OpenAI (json_mode)")
    oai_text = await _oai_complete(messages, model_key, max_tokens, temperature, json_mode=True)
    return _extract_json(oai_text)


async def stream_text(
    messages: list[dict],
    model_key: str = "teach",
    max_tokens: int = 500,
    temperature: float = 0.4,
) -> AsyncGenerator[str, None]:
    """
    Streaming completion.
    Tries Ollama streaming first; falls back to non-streaming complete() on failure.
    """
    model = OLLAMA_MODELS.get(model_key, "llama3.1:8b")
    stream_payload = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
        "stream":      True,
    }

    for base_url in _ollama_endpoints():
        url = f"{base_url}/v1/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=stream_payload) as resp:
                    if not resp.is_success:
                        print(f"[OLLAMA stream] {base_url} → {resp.status_code} — trying next")
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
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield token
                                tokens_yielded += 1
                        except json.JSONDecodeError:
                            continue
                    if tokens_yielded > 0:
                        return
        except Exception as e:
            print(f"[OLLAMA stream] {base_url} error: {e} — trying next")
            continue

    # Fallback: non-streaming complete (tries CF and OpenAI too)
    print(f"[CLIENT] Ollama stream failed — falling back to non-streaming")
    text = await complete(messages, model_key=model_key, max_tokens=max_tokens, temperature=temperature)
    yield text


async def embed(text: str) -> list[float]:
    """Generate embedding using @cf/baai/bge-m3."""
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CF_MODELS['embed']}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=_cf_headers(), json={"text": [text]})
        resp.raise_for_status()
    result = resp.json().get("result", {})
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
    print(f"[OAI] Using {oai_model} for '{model_key}'")
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content.strip()
