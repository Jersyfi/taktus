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
