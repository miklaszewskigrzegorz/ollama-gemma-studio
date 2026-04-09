# =============================================================================
# Makefile — Local LLM Assistant
# Usage: make <target>
# Requires: make, Python 3.11+, Ollama
# =============================================================================

PYTHON  := python3
VENV    := .venv
PIP     := $(VENV)/bin/pip
APP     := $(VENV)/bin/python app.py
MODEL   := gemma4:e2b

.DEFAULT_GOAL := help

# ── Setup ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  Local LLM Assistant — available commands"
	@echo ""
	@echo "  make setup        Create venv + install dependencies"
	@echo "  make model        Pull default Ollama model ($(MODEL))"
	@echo "  make env          Copy .env.example → .env (edit before use)"
	@echo "  make run          Start the app"
	@echo "  make search-up    Start SearXNG (Docker)"
	@echo "  make search-down  Stop SearXNG"
	@echo "  make test         Run tests"
	@echo "  make update       Update all Python dependencies"
	@echo "  make clean        Remove venv and cache files"
	@echo ""

.PHONY: setup
setup: $(VENV)/bin/activate
	@echo "Setup complete. Run: make run"

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $(VENV)/bin/activate

.PHONY: env
env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo ".env created from .env.example — edit it before running the app."; \
	else \
		echo ".env already exists."; \
	fi

.PHONY: model
model:
	ollama pull $(MODEL)

# ── Run ───────────────────────────────────────────────────────────────────────

.PHONY: run
run:
	@docker compose -f docker-compose.searxng.yml up -d 2>/dev/null \
		&& echo "SearXNG started at http://localhost:8888" \
		|| echo "Docker not available — using DuckDuckGo fallback"
	SEARXNG_URL=http://localhost:8888 $(APP)

# ── Search (SearXNG via Docker) ───────────────────────────────────────────────

.PHONY: search-up
search-up:
	docker compose -f docker-compose.searxng.yml up -d
	@echo "SearXNG running at http://localhost:8888"

.PHONY: search-down
search-down:
	docker compose -f docker-compose.searxng.yml down

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test
test:
	$(VENV)/bin/pytest tests/ -v

.PHONY: test-cov
test-cov:
	$(VENV)/bin/pytest tests/ -v --tb=short

# ── Maintenance ───────────────────────────────────────────────────────────────

.PHONY: update
update:
	$(PIP) install --upgrade -r requirements.txt
	@echo "Dependencies updated."

.PHONY: update-model
update-model:
	ollama pull $(MODEL)
	@echo "Model updated."

.PHONY: clean
clean:
	rm -rf $(VENV) __pycache__ .pytest_cache
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

.PHONY: backup
backup:
	@TS=$$(date +%Y%m%d_%H%M%S); \
	mkdir -p _priv_backups; \
	tar -czf _priv_backups/backup_$$TS.tar.gz memory/ logs/ schedule.json 2>/dev/null || true; \
	echo "Backup saved to _priv_backups/backup_$$TS.tar.gz"
