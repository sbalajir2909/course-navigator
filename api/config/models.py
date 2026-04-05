"""
api/config/models.py
Central model configuration for all LLM and embedding calls.
"""
import os

# Ollama base URL — points at Gautschi tunnel (port 11435) or local Ollama (port 11434)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435/v1")

# Task-specific models
VALIDATE_MODEL = "qwen2.5:72b"   # strict grading needs the larger model
TEACH_MODEL    = "llama3.1:8b"
COURSE_MODEL   = "llama3.1:8b"
EMBED_MODEL    = "bge-m3"

# OpenAI fallback models (used only when Ollama is unreachable)
OAI_VALIDATE_MODEL = "gpt-4o"
OAI_DEFAULT_MODEL  = "gpt-4o-mini"
