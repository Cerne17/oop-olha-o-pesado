#!/usr/bin/env bash
# scripts/run.sh -- launch the computer module for a given phase.
#
# Usage:
#   bash scripts/run.sh <phase>
#   bash scripts/run.sh 1     # manual / TCP emulator
#   bash scripts/run.sh 2     # manual / physical robot BT
#   bash scripts/run.sh 3     # autonomous / physical robot + CAM BT
#
# Must be run from the repository root.
# Activates .venv automatically if it exists.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GRN}[run]${NC} $*"; }
warn()  { echo -e "${YLW}[run]${NC} $*"; }
error() { echo -e "${RED}[run]${NC} $*" >&2; }

# --------------------------------------------------------------------------- #
# Validate arguments                                                           #
# --------------------------------------------------------------------------- #

if [[ $# -lt 1 ]]; then
    error "Usage: bash scripts/run.sh <phase>  (1, 2, or 3)"
    exit 1
fi

PHASE="$1"

if [[ "$PHASE" != "1" && "$PHASE" != "2" && "$PHASE" != "3" ]]; then
    error "Invalid phase '$PHASE'. Must be 1, 2, or 3."
    exit 1
fi

# --------------------------------------------------------------------------- #
# Ensure we are in the repo root                                               #
# --------------------------------------------------------------------------- #

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# --------------------------------------------------------------------------- #
# Activate virtual environment                                                 #
# --------------------------------------------------------------------------- #

if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source ".venv/bin/activate"
    info "Virtual environment activated"
elif [[ -f "venv/bin/activate" ]]; then
    source "venv/bin/activate"
    info "Virtual environment activated"
else
    warn "No .venv found -- using system Python. Run: python -m venv .venv && pip install -e ."
fi

# --------------------------------------------------------------------------- #
# Phase descriptions                                                           #
# --------------------------------------------------------------------------- #

case "$PHASE" in
    1) DESC="manual control / TCP loopback to robot emulator" ;;
    2) DESC="manual control / physical robot over Bluetooth" ;;
    3) DESC="autonomous vision / physical robot + CAM over Bluetooth" ;;
esac

info "Starting phase ${PHASE}: ${DESC}"

# --------------------------------------------------------------------------- #
# Phase-specific pre-flight checks                                             #
# --------------------------------------------------------------------------- #

if [[ "$PHASE" == "1" ]]; then
    info "Tip: start the robot emulator first in another terminal:"
    info "     python emulator/src/main.py --port 5001"
    echo ""
fi

if [[ "$PHASE" == "2" || "$PHASE" == "3" ]]; then
    warn "Make sure the robot ESP32 is paired and powered on before continuing."
fi

if [[ "$PHASE" == "3" ]]; then
    warn "Make sure the CAM ESP32 is also paired and powered on."
fi

# --------------------------------------------------------------------------- #
# Launch                                                                       #
# --------------------------------------------------------------------------- #

exec python -m computer.main --phase "$PHASE"
