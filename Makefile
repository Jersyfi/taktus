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

# The project environment. Every target that runs a tool from it depends on `env`, so that a
# fresh checkout needs no `make install` first: the stamp is older than pyproject.toml or
# uv.lock, or absent, and `uv sync` runs once. `make install` forces the sync.
ENV_STAMP := $(or $(UV_PROJECT_ENVIRONMENT),.venv)/.synced

$(ENV_STAMP): pyproject.toml uv.lock | need-uv
	$(UV) sync --all-extras
	@touch $@

env: $(ENV_STAMP) ## Ensure the project environment is installed and current

install: need-uv ## Create or refresh the environment
	$(UV) sync --all-extras
	@touch $(ENV_STAMP)

# The gate directories run under their own targets; `make gates` runs every test exactly once.
test: env ## Unit and domain tests — everything under tests/ that is not a gate
	$(UV) run tools/gate.py test tests $(foreach g,architecture conformance governance exactness,--ignore=tests/$(g))

gate-contracts: need-uv ## Schemas are valid 2020-12, examples validate, must-fail examples fail
	$(UV) run tools/validate_contracts.py

gate-arch: env ## Adapter obligation, component boundaries, no product names in the core
	$(UV) run lint-imports
	$(UV) run tools/gate.py architecture tests/architecture

gate-conformance: env ## Contract conformance suite, both contracts: starts the reference worker and connector, runs the suite and the meta-tests, stops them
	$(UV) run tools/gate.py conformance tests/conformance

gate-governance: env ## Anchors hold, limits never breach, least privilege
	$(UV) run tools/gate.py governance tests/governance

gate-exactness: env ## `exact` steps never take their final value from a variable method
	$(UV) run tools/gate.py exactness tests/exactness

gate-docs: need-uv need-git ## A contract or behaviour change must touch its documentation
	$(UV) run tools/checkdocs.py $(if $(BASE),--base $(BASE))

gate-secrets: need-gitleaks ## No secret value may ever enter this public repository
	gitleaks detect --no-banner --redact

gate-decisions: need-uv ## Decision requests are complete, recorded, and a blocking one keeps its pull request a draft; notices have their evidence
	$(UV) run tools/check_decisions.py

gate-adrs: need-uv ## Every ADR that makes a promise states where the promise ends
	$(UV) run tools/check_adrs.py

gate-status: need-uv ## docs/status.md is current: its shape, its milestone, its date, section 3 as the register generates it, and touched by every change to the state of the project
	$(UV) run tools/check_status.py $(if $(BASE),--base $(BASE))

# The development database (deploy/docker/compose.dev.yml). `db-down` keeps the data volume:
# nothing here deletes data without asking (CLAUDE.md §9).
COMPOSE_DEV := deploy/docker/compose.dev.yml

db-up: need-docker ## Start the development database and wait until it accepts connections
	docker compose -f $(COMPOSE_DEV) up --detach --wait

db-down: need-docker ## Stop the development database; its data volume stays
	docker compose -f $(COMPOSE_DEV) down

# Self-hosting (deploy/docker/compose.yml): Taktus and PostgreSQL, two containers, in one
# command. `up` writes the secret files once (random password, never committed), builds the
# image and waits until readiness answers. `down` stops the containers; every volume stays.
# `up-dev` layers the reference worker over it (compose.reference-worker.yml), in its own
# image, for trying a bundle out; the control plane image carries no worker (DEC-0011).
COMPOSE := deploy/docker/compose.yml
COMPOSE_WORKER := deploy/docker/compose.reference-worker.yml

up: need-docker ## Bring Taktus up: two containers, migrations applied, ready
	deploy/docker/secrets.sh
	docker compose -f $(COMPOSE) up --build --detach --wait

up-dev: need-docker ## The same, plus the reference worker in its own image, for development
	deploy/docker/secrets.sh
	docker compose -f $(COMPOSE) -f $(COMPOSE_WORKER) up --build --detach --wait

down: need-docker ## Stop the containers, with or without the reference worker; the volumes stay
	docker compose -f $(COMPOSE) -f $(COMPOSE_WORKER) down

verify-compose: need-docker ## From nothing: up with the reference worker, the control plane image checked for worker code, a run end to end, the container killed and restarted, the run resumed
	deploy/docker/verify.sh

migrate: env ## Bring the database named by TAKTUS_DATABASE_URL to the current schema
	$(UV) run alembic -c migrations/alembic.ini upgrade head

lint: env ## Static analysis and types
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

generate: env ## Regenerate what is generated: api/openapi.yaml from the REST interface, section 3 of docs/status.md from the register (tools/README.md)
	$(UV) run python tools/generate.py
	$(UV) run tools/check_status.py --write

gates: lint gate-contracts gate-arch gate-conformance gate-governance gate-exactness gate-docs gate-secrets gate-decisions gate-adrs gate-status test ## Everything CI runs

.PHONY: help doctor env install test gate-contracts gate-arch gate-conformance gate-governance gate-exactness gate-docs gate-secrets gate-decisions gate-adrs gate-status db-up db-down up up-dev down verify-compose migrate lint generate gates
