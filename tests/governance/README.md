# Governance tests

Anchors hold, limits are never breached, least privilege throughout (`docs/architecture/governance.md`).

- `test_egress.py`, `test_execution_isolation.py`: the correction anchor's trigger and the
  execution rule of ADR-0002.
- `test_chart.py`: the chart under `deploy/k8s/chart`, rendered with helm and read back — what
  the deployment identity may install, the admission labels, default-deny both ways, Taktus's
  Role, no token in a job, secrets as files only, versions as image tags — and the values files
  free of values, hostnames and addresses. It needs helm: `make helm` installs the pinned
  version; without it the chart's tests skip, and under `TAKTUS_REQUIRE_HELM` (CI) they fail.
- `test_image_workflow.py`: the release images are built on a tag only, pushed only where a
  registry is named, and never deployed.
- `test_autonomy.py`, `test_raise.py`: autonomy levels 1 to 3 at the step boundary (UC-7.1,
  ADR-0039) — the lowest of the process's and its actions' levels holds, a step at level 2
  waits for a person's confirmation, a step that acts at level 1 is proposed and never
  executed, from level 3 only a verified adapter serves; no level switches off the stop, the
  reports or the escalation; a raise needs a person's approval and the quality history, and
  nothing stores a version without asking for both.
