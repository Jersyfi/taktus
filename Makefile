.DEFAULT_GOAL := help
UV ?= uv

help: ## Show targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n",$$1,$$2}'

install: ## Create the environment
	$(UV) sync --all-extras

test: ## Unit and domain tests
	$(UV) run tools/gate.py test tests

gate-contracts: ## Schemas are valid 2020-12, examples validate, must-fail examples fail
	$(UV) run tools/validate_contracts.py

gate-arch: ## Adapter obligation, component boundaries, no product names in the core
	$(UV) run lint-imports
	$(UV) run tools/gate.py architecture tests/architecture

gate-conformance: ## Contract conformance suite
	$(UV) run tools/gate.py conformance tests/conformance

gate-governance: ## Anchors hold, limits never breach, least privilege
	$(UV) run tools/gate.py governance tests/governance

gate-exactness: ## `exact` steps never take their final value from a variable method
	$(UV) run tools/gate.py exactness tests/exactness

gate-docs: ## A contract or behaviour change must touch its documentation
	$(UV) run tools/checkdocs.py $(if $(BASE),--base $(BASE))

gate-secrets: ## No secret value may ever enter this public repository
	gitleaks detect --no-banner --redact

gate-decisions: ## Decision requests are complete, recorded, and a blocking one keeps its pull request a draft
	$(UV) run tools/check_decisions.py

lint: ## Static analysis and types
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

generate: ## Regenerate the shared kernel and API types from contracts/
	$(UV) run python tools/generate.py

gates: lint gate-contracts gate-arch gate-conformance gate-governance gate-exactness gate-docs gate-secrets gate-decisions test ## Everything CI runs

.PHONY: help install test gate-contracts gate-arch gate-conformance gate-governance gate-exactness gate-docs gate-secrets gate-decisions lint generate gates
