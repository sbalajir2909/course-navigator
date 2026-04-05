"""
api/db.py
Shared Supabase REST API client using httpx.
All routes import supabase_query from here.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import httpx
from fastapi import HTTPException

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

_supabase_client: httpx.AsyncClient | None = None


def get_supabase_client() -> httpx.AsyncClient:
    global _supabase_client
    if _supabase_client is None or _supabase_client.is_closed:
        _supabase_client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _supabase_client


def _get_headers() -> dict[str, str]:
    """Build Supabase REST headers from environment variables."""
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get_url() -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    return f"{base}/rest/v1"


async def supabase_query(
    table: str,
    method: str = "GET",
    params: Optional[dict[str, Any]] = None,
    json: Optional[Any] = None,
    extra_headers: Optional[dict[str, str]] = None,
) -> Any:
    """
    Execute a Supabase REST API request.

    Args:
        table:         Table name (e.g. "courses").
        method:        HTTP method: GET, POST, PATCH, DELETE.
        params:        Query string parameters (filters, selects, etc.).
        json:          Request body for POST/PATCH.
        extra_headers: Additional headers (e.g. {"Prefer": "resolution=merge-duplicates"}).

    Returns:
        Parsed JSON response (list or dict).

    Raises:
        httpx.HTTPStatusError: On 4xx/5xx responses.
    """
    headers = _get_headers()
    if extra_headers:
        headers.update(extra_headers)

    url = f"{_get_url()}/{table}"

    client = get_supabase_client()
    for attempt in range(3):
        try:
            resp = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
            )
            resp.raise_for_status()

            if resp.status_code == 204 or not resp.content:
                return []
            return resp.json()
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt == 2:
                raise HTTPException(status_code=503, detail="Database timeout — please retry")
            await asyncio.sleep(1)


async def supabase_rpc(
    function_name: str,
    params: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Call a Supabase RPC (stored procedure / function).

    Args:
        function_name: Name of the Postgres function.
        params:        Named parameters dict.

    Returns:
        Parsed JSON response.
    """
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    url = f"{base}/rest/v1/rpc/{function_name}"

    client = get_supabase_client()
    for attempt in range(3):
        try:
            resp = await client.post(url, headers=headers, json=params or {})
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt == 2:
                raise HTTPException(status_code=503, detail="Database timeout — please retry")
            await asyncio.sleep(1)
