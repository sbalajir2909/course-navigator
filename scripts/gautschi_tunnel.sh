#!/usr/bin/env bash
# =============================================================================
# scripts/gautschi_tunnel.sh
# Run this on your LOCAL MAC to forward Gautschi's Ollama port to localhost:11435
#
# Usage:
#   bash scripts/gautschi_tunnel.sh
#
# What it does:
#   SSH tunnel: localhost:11435 → <compute_node>:11434 via gautschi login node
#
# Prerequisites:
#   1. Gautschi Ollama server must be running (see setup_gautschi.sh)
#   2. You need to know the compute node name (e.g. gpu-a001)
#      Find it with:  squeue -u sbalajir   (look at NODELIST column)
# =============================================================================

set -e

GAUTSCHI_USER="sbalajir"
GAUTSCHI_LOGIN="gautschi.rcac.purdue.edu"
LOCAL_PORT=11435          # local port on your Mac
REMOTE_PORT=11434         # Ollama port on the compute node

# ── Find or prompt for compute node ──────────────────────────────────────────
if [[ -n "$1" ]]; then
    COMPUTE_NODE="$1"
else
    echo "Usage: bash gautschi_tunnel.sh <compute_node>"
    echo ""
    echo "To find your compute node:"
    echo "  ssh ${GAUTSCHI_USER}@${GAUTSCHI_LOGIN} 'squeue -u ${GAUTSCHI_USER}'"
    echo ""
    echo "Example:"
    echo "  bash gautschi_tunnel.sh gpu-a001"
    exit 1
fi

echo "=== Opening SSH tunnel ==="
echo "  Local  : localhost:${LOCAL_PORT}"
echo "  Via    : ${GAUTSCHI_LOGIN}"
echo "  Remote : ${COMPUTE_NODE}:${REMOTE_PORT}"
echo ""
echo "Make sure OLLAMA_REMOTE_URL=http://localhost:${LOCAL_PORT} is in your .env"
echo "Press Ctrl+C to close the tunnel."
echo ""

ssh -N -L "${LOCAL_PORT}:${COMPUTE_NODE}:${REMOTE_PORT}" \
    "${GAUTSCHI_USER}@${GAUTSCHI_LOGIN}"
