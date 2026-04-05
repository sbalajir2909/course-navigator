#!/usr/bin/env bash
# =============================================================================
# scripts/setup_gautschi.sh
#
# PURPOSE: Install Ollama + pull models on Purdue Gautschi cluster.
#          No sudo required — installs entirely to user-space.
#
# STEP 1: Run this on the LOGIN NODE  →  installs Ollama binary
# STEP 2: Get a GPU compute node      →  start server, pull models
# STEP 3: On your Mac                 →  run gautschi_tunnel.sh
#
# USAGE (on Gautschi login node):
#   bash setup_gautschi.sh
# =============================================================================

set -euo pipefail

OLLAMA_BIN="${HOME}/bin/ollama"
SCRATCH_MODELS="${SCRATCH}/ollama/models"

# ── Step 1: Install Ollama binary (no sudo) ───────────────────────────────────
echo "=== [1/3] Installing Ollama binary to ~/bin ==="

mkdir -p "${HOME}/bin"

# Download the Linux x86-64 binary directly (no installer script = no sudo needed)
curl -L --progress-bar \
    "https://ollama.com/download/ollama-linux-amd64" \
    -o "${OLLAMA_BIN}"
chmod +x "${OLLAMA_BIN}"

echo "Installed: ${OLLAMA_BIN}"
"${OLLAMA_BIN}" --version

# ── Step 2: Persist env vars ──────────────────────────────────────────────────
echo ""
echo "=== [2/3] Persisting env vars in ~/.bashrc ==="

mkdir -p "${SCRATCH_MODELS}"

# Only add if not already there
if ! grep -q "OLLAMA_MODELS" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc << BASHRC

# ── Ollama (added by setup_gautschi.sh) ─────────────────────────────────────
export PATH="\${HOME}/bin:\${PATH}"
export OLLAMA_MODELS="\${SCRATCH}/ollama/models"
export OLLAMA_HOST="0.0.0.0:11434"
BASHRC
    echo "Added to ~/.bashrc"
fi

# Apply for this session
export PATH="${HOME}/bin:${PATH}"
export OLLAMA_MODELS="${SCRATCH_MODELS}"
export OLLAMA_HOST="0.0.0.0:11434"

echo "OLLAMA_MODELS=${OLLAMA_MODELS}"

# ── Step 3: Write the batch job and pull script ───────────────────────────────
echo ""
echo "=== [3/3] Writing job scripts ==="

# --- SLURM batch job: persistent Ollama server ---
cat > "${HOME}/ollama_server.sbatch" << 'SBATCH'
#!/usr/bin/env bash
#SBATCH --job-name=ollama_server
#SBATCH --account=mlp
#SBATCH --partition=ai
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=80G
#SBATCH --time=24:00:00
#SBATCH --output=/home/%u/ollama_server_%j.log

export PATH="${HOME}/bin:${PATH}"
export OLLAMA_MODELS="${SCRATCH}/ollama/models"
export OLLAMA_HOST="0.0.0.0:11434"

echo "[$(date)] Ollama server starting on $(hostname) port 11434"
echo "NODE=$(hostname)" > "${HOME}/ollama_node.txt"

"${HOME}/bin/ollama" serve
SBATCH
chmod +x "${HOME}/ollama_server.sbatch"
echo "Wrote: ~/ollama_server.sbatch"

# --- Script to pull models (run inside a GPU session) ---
cat > "${HOME}/ollama_pull_models.sh" << 'PULL'
#!/usr/bin/env bash
# Run inside an interactive GPU session or after submitting ollama_server.sbatch
set -e

export PATH="${HOME}/bin:${PATH}"
export OLLAMA_MODELS="${SCRATCH}/ollama/models"
export OLLAMA_HOST="0.0.0.0:11434"

echo "=== Starting Ollama server in background ==="
"${HOME}/bin/ollama" serve &>/tmp/ollama_pull.log &
OLLAMA_PID=$!
echo "PID: $OLLAMA_PID  —  waiting for server to be ready..."
sleep 8

echo ""
echo "=== Pulling llama3.1:8b  (~5 GB) ==="
"${HOME}/bin/ollama" pull llama3.1:8b

echo ""
echo "=== Pulling qwen2.5:72b  (~47 GB) ==="
"${HOME}/bin/ollama" pull qwen2.5:72b

echo ""
echo "=== Done! Installed models: ==="
"${HOME}/bin/ollama" list

echo ""
echo "Node: $(hostname)"
echo "Add to your Mac .env:  OLLAMA_REMOTE_URL=http://localhost:11435"
echo "Then on your Mac run:  bash scripts/gautschi_tunnel.sh $(hostname)"
PULL
chmod +x "${HOME}/ollama_pull_models.sh"
echo "Wrote: ~/ollama_pull_models.sh"

# ── Print next steps ──────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Setup complete! Next steps:"
echo "============================================================"
echo ""
echo "  Option A — Interactive session (pull models now):"
echo "    sinteractive -N1 -n4 --gres=gpu:1 --mem=80G -t 4:00:00 \\"
echo "                 -A mlp -p ai"
echo "    # once inside the GPU node:"
echo "    bash ~/ollama_pull_models.sh"
echo ""
echo "  Option B — Submit persistent batch server:"
echo "    sbatch ~/ollama_server.sbatch"
echo "    squeue -u \$USER          # wait for RUNNING, note the node name"
echo "    ssh <node>               # ssh onto that node"
echo "    bash ~/ollama_pull_models.sh"
echo ""
echo "  Then on your Mac:"
echo "    bash scripts/gautschi_tunnel.sh <node_name>"
echo "============================================================"
