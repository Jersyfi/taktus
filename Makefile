.DEFAULT_GOAL := help
UV ?= uv

# Every target is declared .PHONY beside itself: one shared list was a line every pull request
# that adds a target rewrote, and two such pull requests conflicted on it (DEC-0027, #392).
.PHONY: help
help: ## Show targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n",$$1,$$2}'

# Every target depends on the tools it needs through need-<tool>. A missing tool then names
# itself, what it is for and how to install it (tools/preflight.sh), instead of failing with
# `make: uv: No such file or directory`.
need-%:
	@tools/preflight.sh $*

.PHONY: doctor
doctor: ## Report the tooling state; non-zero if a required tool is missing
	@tools/preflight.sh --doctor

# The project environment. Every target that runs a tool from it depends on `env`, so that a
# fresh checkout needs no `make install` first: the stamp is older than pyproject.toml or
# uv.lock, or absent, and `uv sync` runs once. `make install` forces the sync.
ENV_STAMP := $(or $(UV_PROJECT_ENVIRONMENT),.venv)/.synced

$(ENV_STAMP): pyproject.toml uv.lock | need-uv
	$(UV) sync --all-extras
	@touch $@

.PHONY: env
env: $(ENV_STAMP) ## Ensure the project environment is installed and current

.PHONY: install
install: need-uv ## Create or refresh the environment
	$(UV) sync --all-extras
	@touch $(ENV_STAMP)

# The two slow suites spread over the machine's cores (`pytest-xdist`, ADR-0096): each worker
# process starts its own workers, connectors and PostgreSQL container, so no test shares state
# with one in another process. `PARALLEL=` runs them in one process; the cap keeps a large
# machine from starting a database per core.
PARALLEL ?= -n auto --maxprocesses=8

# The gate directories run under their own targets; `make gates` runs every test exactly once.
# With BASE, only the tests the change selects run: the test files that import, directly or
# through others, a module the change touches (`tools/lanes.py --tests`, #394, ADR-0096 §3).
# Without it, every test runs. `make verify` passes BASE; CI's lane `test` passes it on a pull
# request and not on a push to `main`.
GATES := architecture conformance governance exactness rehearsal
TEST_TARGETS = $(if $(BASE),$(shell python3 tools/lanes.py --base $(BASE) --tests $(foreach g,$(GATES),--exclude tests/$(g))),tests)

.PHONY: test
test: env ## Unit and domain tests — everything under tests/ that is not a gate, or with BASE only what the change selects; PARALLEL= runs them in one process
	@targets="$(TEST_TARGETS)"; \
	if [ -z "$$targets" ]; then echo "test: the change selects no test"; exit 0; fi; \
	echo "test: $$targets"; \
	$(UV) run tools/gate.py test $$targets $(PARALLEL) -m 'not timing' $(foreach g,$(GATES),--ignore=tests/$(g))

# The tests that assert a bound on wall-clock time, in one process and alone (ADR-0096 §7, #528):
# CI's lane `timing` is a job of its own, and `make verify` runs it last, holding the machine.
# With BASE, only those of the tests the change selects.
.PHONY: timing
timing: env ## The tests marked `timing` (a bound on wall-clock time), alone in one process; with BASE only those the change selects
	@targets="$(TEST_TARGETS)"; \
	if [ -z "$$targets" ]; then echo "timing: the change selects no test"; exit 0; fi; \
	echo "timing: $$targets"; \
	$(UV) run tools/gate.py timing $$targets -m timing $(foreach g,$(GATES),--ignore=tests/$(g))

# The self-development bundles, replayed from their recordings against a database (ADR-0108):
# CI's lane `rehearse`, which `tools/lanes.py` selects for a change to a bundle, a recording or
# the core, and every push to `main` runs. It needs no credential and reaches nothing outside.
.PHONY: rehearse
rehearse: env ## Replay P-01, P-02, P-03 and S-07 from tests/rehearsal/recordings; every step must reach the state it reached when recorded
	$(UV) run tools/gate.py rehearse tests/rehearsal

# The images the container tests need (tests/images.py). Each is built only when its Dockerfile
# or a file it copies changed; an unchanged one is not handed to the builder at all. The tests
# build them the same way on first use; this target does it ahead, with each build's time.
.PHONY: images
images: env need-docker ## Build the test images whose content changed; REBUILD=1 builds them all
	$(UV) run python tests/images.py $(if $(REBUILD),--rebuild)

.PHONY: gate-contracts
gate-contracts: need-uv ## Schemas are valid 2020-12, examples validate, must-fail examples fail
	$(UV) run tools/validate_contracts.py

.PHONY: gate-arch
gate-arch: env ## Adapter obligation, component boundaries, no product names in the core
	$(UV) run lint-imports
	$(UV) run tools/gate.py architecture tests/architecture

.PHONY: gate-conformance
gate-conformance: env ## Contract conformance suite, both contracts: starts the reference worker and connector, runs the suite and the meta-tests, stops them
	$(UV) run tools/gate.py conformance tests/conformance $(PARALLEL)

# The chart's tests (tests/governance/test_chart.py) render it with helm. `make helm` installs the
# pinned version into .tools/bin, which the tests use first; without helm they skip and say so,
# and CI, which runs this target, sets TAKTUS_REQUIRE_HELM so that they cannot.
.PHONY: helm
helm: ## Install the pinned helm into .tools/bin, for the chart's tests (deploy/k8s/chart)
	tools/install_helm.sh

.PHONY: gate-governance
gate-governance: env ## Anchors hold, limits never breach, least privilege; the chart, rendered with helm (`make helm`), and the image workflow
	$(UV) run tools/gate.py governance tests/governance

.PHONY: gate-exactness
gate-exactness: env ## `exact` steps never take their final value from a variable method
	$(UV) run tools/gate.py exactness tests/exactness

.PHONY: gate-docs
gate-docs: need-uv need-git ## A contract or behaviour change must touch its documentation
	$(UV) run tools/checkdocs.py $(if $(BASE),--base $(BASE))

.PHONY: gate-secrets
gate-secrets: need-gitleaks ## No secret value may ever enter this public repository
	gitleaks detect --no-banner --redact

.PHONY: gate-decisions
gate-decisions: need-uv ## Decision requests are complete, recorded, and a blocking one keeps its pull request a draft; notices have their evidence; the index is stored nowhere; with BASE, every record added carries a reserved number
	$(UV) run tools/check_decisions.py $(if $(BASE),--base $(BASE))

.PHONY: gate-adrs
gate-adrs: need-uv ## Every ADR that makes a promise states where the promise ends
	$(UV) run tools/check_adrs.py

.PHONY: gate-status
gate-status: need-uv ## docs/status.md is current: its shape, its milestone, no line every pull request rewrites, section 3 pointing at `make status` rather than storing a list, and touched by every change to the state of the project
	$(UV) run tools/check_status.py $(if $(BASE),--base $(BASE))

.PHONY: gate-vision
gate-vision: need-uv ## The vision layer holds together — the fourteen principles as CLAUDE.md names them, each with why and what it forbids — and every principle is served by a use case
	$(UV) run tools/check_vision.py

# The use case gate runs the named tests of a `verified` use case, so it needs the project
# environment: `uv run python` rather than `uv run <script>`, which would isolate the script.
.PHONY: gate-web
gate-web: ## The web app under web/: packages from the lock file, types, tests, build; skips without Node and says so, unless TAKTUS_REQUIRE_NODE is set
	@tools/web.sh

.PHONY: gate-usecases
gate-usecases: env ## Every use case has a state, a verification condition and a principle; built names tests, verified ones are green; no ADR moved under one unchecked; no requirement changed where it is implemented
	$(UV) run python tools/check_usecases.py $(if $(BASE),--base $(BASE))

# Every documentation, register and architecture gate is fed a deliberate violation in a copy
# of the working tree, and must go red for it (ADR-0096 §6, #395). CI's lane `selftest` runs it
# when a gate's code changes, and on every push to `main`. GATE=gate-adrs runs one gate's cases.
.PHONY: gate-selftest
gate-selftest: env ## Each documentation, register and architecture gate, fed a deliberate violation, goes red for it; fails if one stays green (GATE= one gate)
	$(UV) run python tools/gate_selftest.py $(if $(GATE),--gate $(GATE))

backlog: need-uv ## Print the backlog in the order a session takes it, every unready issue with its reasons; NEXT=1 the next one, ANSWERS=1 the owner's answers to record first (DEC-0051)
	$(UV) run tools/backlog.py $(if $(NEXT),--next) $(if $(ANSWERS),--answers)

.PHONY: usecases
usecases: env ## Print every use case with its component, state and version
	@$(UV) run python tools/check_usecases.py --print

# The development database (deploy/docker/compose.dev.yml). `db-down` keeps the data volume:
# nothing here deletes data without asking (CLAUDE.md §9).
COMPOSE_DEV := deploy/docker/compose.dev.yml

.PHONY: db-up
db-up: need-docker ## Start the development database and wait until it accepts connections
	docker compose -f $(COMPOSE_DEV) up --detach --wait

.PHONY: db-down
db-down: need-docker ## Stop the development database; its data volume stays
	docker compose -f $(COMPOSE_DEV) down

# Self-hosting (deploy/docker/compose.yml): Taktus and PostgreSQL, two containers, in one
# command. `up` writes the secret files once (random password, never committed), builds the
# image and waits until readiness answers. `down` stops the containers; every volume stays.
# `up-dev` layers the reference worker over it (compose.reference-worker.yml), in its own
# image, for trying a bundle out; the control plane image carries no worker (DEC-0011).
COMPOSE := deploy/docker/compose.yml
COMPOSE_WORKER := deploy/docker/compose.reference-worker.yml

.PHONY: up
up: need-docker ## Bring Taktus up: two containers, migrations applied, ready
	deploy/docker/secrets.sh
	docker compose -f $(COMPOSE) up --build --detach --wait

.PHONY: up-dev
up-dev: need-docker ## The same, plus the reference worker in its own image, for development
	deploy/docker/secrets.sh
	docker compose -f $(COMPOSE) -f $(COMPOSE_WORKER) up --build --detach --wait

.PHONY: down
down: need-docker ## Stop the containers, with or without the reference worker; the volumes stay
	docker compose -f $(COMPOSE) -f $(COMPOSE_WORKER) down

.PHONY: verify-compose
verify-compose: need-docker ## From nothing: up with the reference worker, the control plane image checked for worker code, a run end to end, the container killed and restarted, the run resumed
	deploy/docker/verify.sh

.PHONY: verify-upgrade
verify-upgrade: need-docker ## The previous release with a run in every state, upgraded to this checkout; every run resumes at its boundary (TAKTUS_UPGRADE_FROM, _IMAGE, _WORKER_IMAGE; ADR-0124)
	deploy/docker/upgrade.sh

# The chart on a real cluster (#395, the nightly ring): this checkout's image, installed with its
# database into the cluster kubectl points at, migrated, and ready. Needs docker, kind, kubectl
# and helm; deletes nothing.
.PHONY: verify-kind
verify-kind: need-docker ## The chart in a kind cluster: this checkout's image, profile small, its database migrated, the control plane ready (deploy/k8s/kind.sh)
	deploy/k8s/kind.sh

# The backup and the restore by hand against a real database and the backup image (ADR-0087,
# #395): the nightly ring runs it on its own; `make test` runs the same tests among the rest.
.PHONY: verify-backup
verify-backup: env need-docker ## The backup image against a real database, and the restore by hand into a fresh one (tests/deploy)
	$(UV) run tools/gate.py backup tests/deploy

.PHONY: migrate
migrate: env ## Bring the database named by TAKTUS_DATABASE_URL to the current schema
	$(UV) run alembic -c migrations/alembic.ini upgrade head

.PHONY: lint
lint: env ## Static analysis and types, of the product and of the Python tools under tools/
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

.PHONY: generate
generate: env ## Regenerate what is generated and committed: api/openapi.yaml from the REST interface, the web app's test fixtures from reporting (tools/README.md)
	$(UV) run python tools/generate.py

.PHONY: status
status: need-uv ## Print what is needed from the owner, from the register: the last section of every pull request description (DEC-0026)
	@$(UV) run tools/check_status.py --print --ask-host

.PHONY: check
check: need-uv ## The fast local check before a commit: lint, types, architecture, documentation and register gates, and the unit tests (under 60 s)
	$(MAKE) lint gate-arch gate-docs gate-decisions gate-adrs gate-status
	@targets="$$(python3 tools/lanes.py --base $(or $(BASE),origin/main) --tests --within tests/components --within tests/tools --within tests/contract)"; \
	if [ -z "$$targets" ]; then echo "check: the change selects no unit test"; exit 0; fi; \
	$(UV) run pytest -q -p no:randomly $$targets

.PHONY: verify
verify: need-uv need-git ## What CI would select for this change, against BASE (default origin/main); stamps the commit when all passes on a clean tree (ADR-0096 §4)
	@tools/verify.sh

.PHONY: adrs
adrs: need-uv ## Print the index of the ADRs, generated from docs/adr/ (#392)
	@$(UV) run tools/check_adrs.py --index

.PHONY: tree
tree: need-uv ## Print the tree of src/taktus, every module with the first sentence of its docstring (#392)
	@$(UV) run tools/tree.py

.PHONY: register
register: need-uv ## Print the register's index, generated from the records: every provided need, notice and record (DEC-0189 rule 6)
	@$(UV) run tools/check_decisions.py --index

.PHONY: reserve
reserve: need-uv need-git ## Reserve a record number on the remote before writing the record: KIND=DEC|NTC|NEED the next free one, ID=NTC-0207 exactly that one (DEC-0189 rule 6)
	@$(UV) run tools/reserve.py $(if $(ID),--id $(ID),--kind $(KIND))

.PHONY: gates
gates: lint gate-contracts gate-arch gate-conformance gate-governance gate-exactness gate-docs gate-secrets gate-decisions gate-adrs gate-status gate-vision gate-usecases gate-web gate-selftest test timing rehearse ## Everything CI runs
