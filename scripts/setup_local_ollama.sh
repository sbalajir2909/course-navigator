#!/usr/bin/env bash
# =============================================================================
# scripts/setup_local_ollama.sh
# Install Ollama on your local Mac and pull the required models.
#
# Usage:
#   bash scripts/setup_local_ollama.sh
# =============================================================================

set -e

echo "=== Step 1: Install Ollama on Mac ==="
if command -v ollama &>/dev/null; then
    echo "Ollama already installed: $(ollama --version)"
else
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

echo ""
echo "=== Step 2: Start Ollama server (background) ==="
if pgrep -x ollama &>/dev/null; then
    echo "Ollama is already running."
else
    echo "Starting ollama serve in background..."
    ollama serve &>/tmp/ollama.log &
    sleep 3
    echo "Ollama started (logs: /tmp/ollama.log)"
fi

echo ""
echo "=== Step 3: Pull models ==="

echo ""
echo "Pulling llama3.1:8b  (teach / course / assessment / grading / faithfulness)..."
ollama pull llama3.1:8b

echo ""
echo "Pulling qwen2.5:72b  (validation — needs ~40 GB free disk + ~24 GB RAM)..."
echo "If your Mac doesn't have enough RAM, skip this and use the Gautschi tunnel."
read -p "Pull qwen2.5:72b locally? [y/N] " yn
if [[ "${yn,,}" == "y" ]]; then
    ollama pull qwen2.5:72b
else
    echo "Skipped qwen2.5:72b locally — validation will fall through to Gautschi tunnel or OpenAI."
fi

echo ""
echo "=== Done! Models available: ==="
ollama list

echo ""
echo "Add to your .env:"
echo "  OLLAMA_LOCAL_URL=http://localhost:11434"
echo "  OLLAMA_REMOTE_URL=http://localhost:11435   # only if using Gautschi tunnel"
