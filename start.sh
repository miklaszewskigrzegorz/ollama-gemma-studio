#!/usr/bin/env bash
# =============================================================================
# start.sh — macOS / Linux quick launcher for Local LLM Assistant
# Usage: chmod +x start.sh && ./start.sh
# =============================================================================

set -e
cd "$(dirname "$0")"

# ── Python ────────────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null)
        if [ "$VER" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11+ not found."
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3.12 python3.12-venv"
    exit 1
fi

# ── Ollama ────────────────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    echo "ERROR: Ollama not found."
    echo "  Install: curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "Checking dependencies..."
pip install -r requirements.txt -q

# ── .env ──────────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# ── Docker + SearXNG (optional) ───────────────────────────────────────────────
echo ""
echo "Checking Docker..."

_start_docker_mac() {
    open -a Docker 2>/dev/null || true
    echo "Starting Docker Desktop (up to 60 seconds)..."
    for i in $(seq 1 12); do
        sleep 5
        docker info &>/dev/null && return 0
        echo "  Still waiting... ($i/12)"
    done
    return 1
}

_start_docker_linux() {
    if command -v systemctl &>/dev/null; then
        sudo systemctl start docker 2>/dev/null || true
        for i in $(seq 1 6); do
            sleep 3
            docker info &>/dev/null && return 0
        done
    fi
    return 1
}

if docker info &>/dev/null; then
    echo "Docker is running."
    DOCKER_OK=true
else
    OS="$(uname -s)"
    if [ "$OS" = "Darwin" ]; then
        _start_docker_mac && DOCKER_OK=true || DOCKER_OK=false
    elif [ "$OS" = "Linux" ]; then
        _start_docker_linux && DOCKER_OK=true || DOCKER_OK=false
    else
        DOCKER_OK=false
    fi
fi

if [ "$DOCKER_OK" = "true" ]; then
    echo "Starting SearXNG..."
    if docker compose -f docker-compose.searxng.yml up -d &>/dev/null; then
        echo "SearXNG ready at http://localhost:8888"
        export SEARXNG_URL=http://localhost:8888
    else
        echo "WARNING: Could not start SearXNG. Using DuckDuckGo fallback."
    fi
else
    echo "Docker not available. Using DuckDuckGo fallback."
fi

# ── Start app ─────────────────────────────────────────────────────────────────
echo ""
echo "Starting Local LLM Assistant..."
echo "Press Ctrl+C to stop."
echo ""
python app.py
