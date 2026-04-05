"""
main.py
Assign B2B — FastAPI application entry point.

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

After filling in your .env file with:
    OPENAI_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
    TAVILY_API_KEY
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

# Load .env before anything else so all submodules see the env vars
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Route routers
from api.routes.ingest import router as ingest_router
from api.routes.courses import router as courses_router
from api.routes.teach import router as teach_router
from api.routes.dashboard import router as dashboard_router
from api.routes.ground import router as ground_router
from api.routes.auth import router as auth_router

# ─────────────────────────────────────────────────────────
# App initialisation
# ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Assign B2B",
    description=(
        "EdTech platform where professors upload course materials and the system "
        "generates structured courses with adaptive learning via a Socratic teaching loop."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ─────────────────────────────────────────────────────────
# CORS middleware — allow all origins for hackathon
# ─────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────
# Register routers
# ─────────────────────────────────────────────────────────

app.include_router(ingest_router)
app.include_router(courses_router)
app.include_router(teach_router)
app.include_router(dashboard_router)
app.include_router(ground_router)
app.include_router(auth_router)

# ─────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────

@app.get("/health", tags=["system"], summary="Health check")
async def health_check() -> JSONResponse:
    """
    Basic health check endpoint.

    Returns service status and environment variable presence
    (without leaking actual key values).
    """
    return JSONResponse(
        content={
            "status": "ok",
            "service": "Assign B2B",
            "version": "1.0.0",
            "env": {
                "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
                "SUPABASE_URL": bool(os.getenv("SUPABASE_URL")),
                "SUPABASE_SERVICE_KEY": bool(os.getenv("SUPABASE_SERVICE_KEY")),
                "TAVILY_API_KEY": bool(os.getenv("TAVILY_API_KEY")),
            },
        }
    )


# ─────────────────────────────────────────────────────────
# Root
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["system"], summary="Root")
async def root() -> JSONResponse:
    """Returns API name and docs link."""
    return JSONResponse(
        content={
            "api": "Assign B2B",
            "docs": "/docs",
            "health": "/health",
        }
    )


# ─────────────────────────────────────────────────────────
# Startup event
# ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup() -> None:
    """Print startup summary including all registered routes."""
    routes = [
        route
        for route in app.routes
        if hasattr(route, "methods")  # Exclude mount points
    ]
    print("\n" + "=" * 60)
    print("  Assign B2B — Backend started")
    print("=" * 60)
    print(f"  Registered routes: {len(routes)}")
    for route in sorted(routes, key=lambda r: getattr(r, "path", "")):
        methods = ", ".join(getattr(route, "methods", set()))
        path = getattr(route, "path", "")
        print(f"    [{methods:20s}] {path}")
    print("=" * 60)
    print(f"  Docs:   http://localhost:8000/docs")
    print(f"  Health: http://localhost:8000/health")
    print("=" * 60 + "\n")
