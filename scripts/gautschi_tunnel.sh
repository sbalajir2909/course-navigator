#!/usr/bin/env bash
# =============================================================================
# scripts/gautschi_tunnel.sh
# Run on your LOCAL MAC to forward Gautschi Ollama → localhost:11435
#
# Usage:
#   bash scripts/gautschi_tunnel.sh <compute_node>
#
# Example:
#   bash scripts/gautschi_tunnel.sh g001
#
# Find your compute node name:
#   ssh sbalajir@gautschi.rcac.purdue.edu 'squeue -u sbalajir'
#   look at the NODELIST column
#
# Once tunnel is open, add to your .env:
#   OLLAMA_REMOTE_URL=http://localhost:11435
# =============================================================================

GAUTSCHI_USER="sbalajir"
GAUTSCHI_LOGIN="gautschi.rcac.purdue.edu"
LOCAL_PORT=11435
REMOTE_PORT=11434

if [[ -z "$1" ]]; then
    # Try to read node from the file written by ollama_server.sbatch
    NODE=$(ssh "${GAUTSCHI_USER}@${GAUTSCHI_LOGIN}" \
        'cat $HOME/ollama_node.txt 2>/dev/null | grep NODE | cut -d= -f2' 2>/dev/null || true)
    if [[ -z "$NODE" ]]; then
        echo "Usage: bash gautschi_tunnel.sh <compute_node>"
        echo ""
        echo "To find your node:"
        echo "  ssh ${GAUTSCHI_USER}@${GAUTSCHI_LOGIN} 'squeue -u ${GAUTSCHI_USER}'"
        exit 1
    fi
    echo "Auto-detected node from cluster: ${NODE}"
else
    NODE="$1"
fi

echo "============================================================"
echo "  Opening SSH tunnel"
echo "  localhost:${LOCAL_PORT}  →  ${NODE}:${REMOTE_PORT}"
echo "  via ${GAUTSCHI_LOGIN}"
echo ""
echo "  OLLAMA_REMOTE_URL=http://localhost:${LOCAL_PORT}"
echo "  Press Ctrl+C to close."
echo "============================================================"
echo ""

# -J uses the login node as a jump host to reach the compute node directly
ssh -N \
    -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" \
    -J "${GAUTSCHI_USER}@${GAUTSCHI_LOGIN}" \
    "${GAUTSCHI_USER}@${NODE}"
