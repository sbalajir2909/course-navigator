#!/usr/bin/env bash
# =============================================================================
# scripts/setup_gautschi.sh
# Run this ON the Gautschi cluster (after ssh in) to install Ollama + models.
#
# Usage:
#   ssh sbalajir@gautschi.rcac.purdue.edu
#   bash setup_gautschi.sh
#
# What it does:
#   1. Installs Ollama to ~/bin (no root needed)
#   2. Sets OLLAMA_MODELS to $SCRATCH/ollama/models  (avoids home quota)
#   3. Submits a persistent GPU batch job that runs Ollama as a server
#   4. Pulls llama3.1:8b and qwen2.5:72b into scratch
# =============================================================================

set -e

SCRATCH_MODELS="${SCRATCH}/ollama/models"
OLLAMA_BIN="${HOME}/bin/ollama"
JOB_SCRIPT="${HOME}/ollama_server.sh"

echo "=== Step 1: Install Ollama (user-space) ==="
mkdir -p "${HOME}/bin"
curl -L https://ollama.com/download/ollama-linux-amd64 -o "${OLLAMA_BIN}"
chmod +x "${OLLAMA_BIN}"
echo "Ollama installed at ${OLLAMA_BIN}"

# Add ~/bin to PATH for this session
export PATH="${HOME}/bin:${PATH}"

echo ""
echo "=== Step 2: Configure model storage on scratch (avoids home quota) ==="
mkdir -p "${SCRATCH_MODELS}"
export OLLAMA_MODELS="${SCRATCH_MODELS}"
echo "Models will be stored at ${SCRATCH_MODELS}"

# Persist env vars in ~/.bashrc
if ! grep -q "OLLAMA_MODELS" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# Ollama — added by setup_gautschi.sh" >> ~/.bashrc
    echo "export PATH=\"\${HOME}/bin:\${PATH}\"" >> ~/.bashrc
    echo "export OLLAMA_MODELS=\"\${SCRATCH}/ollama/models\"" >> ~/.bashrc
    echo "export OLLAMA_HOST=\"0.0.0.0:11434\"" >> ~/.bashrc
fi

echo ""
echo "=== Step 3: Write SLURM batch job for persistent Ollama server ==="
cat > "${JOB_SCRIPT}" << 'SLURM'
#!/usr/bin/env bash
#SBATCH --job-name=ollama_server
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=80G
#SBATCH --time=24:00:00
#SBATCH --output=%HOME/ollama_server_%j.log

export PATH="${HOME}/bin:${PATH}"
export OLLAMA_MODELS="${SCRATCH}/ollama/models"
export OLLAMA_HOST="0.0.0.0:11434"

echo "[$(date)] Starting Ollama server on $(hostname) port 11434"
ollama serve
SLURM

chmod +x "${JOB_SCRIPT}"
echo "Job script written to ${JOB_SCRIPT}"

echo ""
echo "=== Step 4: Pull models (run on a GPU node via sinteractive or inside the job) ==="
echo ""
echo "Option A — pull right now with sinteractive:"
echo "  sinteractive -N1 -n4 --gres=gpu:1 --mem=80G -t 2:00:00"
echo "  Then inside the session:"
echo "    export PATH=\${HOME}/bin:\${PATH}"
echo "    export OLLAMA_MODELS=\${SCRATCH}/ollama/models"
echo "    ollama serve &"
echo "    sleep 5"
echo "    ollama pull llama3.1:8b"
echo "    ollama pull qwen2.5:72b"
echo ""
echo "Option B — submit the server job and pull after it starts:"
echo "  sbatch ${JOB_SCRIPT}"
echo "  squeue -u \$USER          # wait for it to be RUNNING, note the node name"
echo "  ssh <compute_node>         # ssh to that node"
echo "    export PATH=\${HOME}/bin:\${PATH}"
echo "    export OLLAMA_MODELS=\${SCRATCH}/ollama/models"
echo "    ollama pull llama3.1:8b"
echo "    ollama pull qwen2.5:72b"

echo ""
echo "=== Done! Next: run setup_gautschi_tunnel.sh on your Mac ==="
