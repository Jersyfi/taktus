.DEFAULT_GOAL := help
UV ?= uv

help: ## Show targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n",$$1,$$2}'

# Every target depends on the tools it needs through need-<tool>. A missing tool then names
# itself, what it is for and how to install it (tools/preflight.sh), instead of failing with
# `make: uv: No such file or directory`.
need-%:
	@tools/preflight.sh $*

doctor: ## Report the tooling state; non-zero if a required tool is missing
	@tools/preflight.sh --doctor

install: need-uv ## Create the environment
	$(UV) sync --all-extras

# The gate directories run under their own targets; `make gates` runs every test exactly once.
test: need-uv ## Unit and domain tests — everything under tests/ that is not a gate
	$(UV) run tools/gate.py test tests $(foreach g,architecture conformance governance exactness,--ignore=tests/$(g))

gate-contracts: need-uv ## Schemas are valid 2020-12, examples validate, must-fail examples fail
	$(UV) run tools/validate_contracts.py

gate-arch: need-uv ## Adapter obligation, component boundaries, no product names in the core
	$(UV) run lint-imports
	$(UV) run tools/gate.py architecture tests/architecture

gate-conformance: need-uv ## Contract conformance suite: starts the reference worker, runs the suite and the meta-test, stops it
	$(UV) run tools/gate.py conformance tests/conformance

gate-governance: need-uv ## Anchors hold, limits never breach, least privilege
	$(UV) run tools/gate.py governance tests/governance

gate-exactness: need-uv ## `exact` steps never take their final value from a variable method
	$(UV) run tools/gate.py exactness tests/exactness

gate-docs: need-uv ## A contract or behaviour change must touch its documentation
	$(UV) run tools/checkdocs.py $(if $(BASE),--base $(BASE))

gate-secrets: need-gitleaks ## No secret value may ever enter this public repository
	gitleaks detect --no-banner --redact

gate-decisions: need-uv ## Decision requests are complete, recorded, and a blocking one keeps its pull request a draft
	$(UV) run tools/check_decisions.py

lint: need-uv ## Static analysis and types
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

generate: need-uv ## Regenerate the shared kernel and API types from contracts/
	$(UV) run python tools/generate.py

gates: lint gate-contracts gate-arch gate-conformance gate-governance gate-exactness gate-docs gate-secrets gate-decisions test ## Everything CI runs

.PHONY: help doctor install test gate-contracts gate-arch gate-conformance gate-governance gate-exactness gate-docs gate-secrets gate-decisions lint generate gates
