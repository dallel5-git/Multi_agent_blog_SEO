.DEFAULT_GOAL := help
PY ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help install install-dev check test lint fmt dry-run offline offline-pilotage run index runs graph dashboard dashboard-pilotage scheduler clean

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV):
	$(PY) -m venv $(VENV)

install: $(VENV) ## Installe les dépendances de production
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/pip install -e .

install-dev: $(VENV) ## Installe les dépendances de développement
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements-dev.txt
	$(BIN)/pip install -e .

check: ## Vérifie la configuration et les dépendances
	$(BIN)/blogseo check

offline: ## Test complet SANS clé API et SANS réseau (recommandé en premier)
	$(BIN)/blogseo run --dry-run --offline --print

offline-pilotage: ## Test complet du pilotage SANS clé API et SANS réseau
	$(BIN)/pytest tests/unit/test_pilotage_offline_e2e.py tests/unit/test_bot_conversation_e2e.py -v

dry-run: ## Run complet avec les vrais LLM, mais sans rien publier
	$(BIN)/blogseo run --dry-run

run: ## Run complet avec validation Telegram
	$(BIN)/blogseo run

index: ## (Ré)indexe les articles existants pour l'anti-doublon
	$(BIN)/blogseo index

runs: ## Liste les derniers runs
	$(BIN)/blogseo runs

graph: ## Affiche le diagramme du pipeline
	$(BIN)/blogseo graph

dashboard: ## Génère le tableau de bord HTML local et l'ouvre dans le navigateur
	$(BIN)/blogseo dashboard --open

scheduler: ## Démarre le planificateur local (hebdomadaire / chaque semaine)
	$(BIN)/python -m blogseo.interfaces.scheduler

dashboard-pilotage: ## Tableau de bord Streamlit du pilotage (lecture seule)
	$(BIN)/streamlit run src/pilotage/dashboard/app.py

test: ## Lance les tests unitaires
	$(BIN)/pytest -v

test-cov: ## Tests avec rapport de couverture
	$(BIN)/pytest --cov --cov-report=term-missing

lint: ## Analyse statique
	$(BIN)/ruff check src tests

fmt: ## Corrige automatiquement ce qui peut l'être
	$(BIN)/ruff check --fix src tests

clean: ## Supprime les artefacts de build et les caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist *.egg-info
