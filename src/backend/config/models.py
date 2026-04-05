"""
config/models.py - Model and service configuration
"""
import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435/v1")
