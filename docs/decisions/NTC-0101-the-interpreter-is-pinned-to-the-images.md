# NTC-0101 — The interpreter is pinned to the image's

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-10
**Raised in:** the pull request that adds `.python-version`

## 1. What was decided

The gates run on the Python version the control plane's image ships, 3.13.

- **Old:** nothing named a version. `uv` took the newest interpreter it could download. On
  2026-10-10 that became 3.15.0, and `make install` failed on every branch: the database driver
  `psycopg-binary` 3.3.5 has no build for 3.15. Before that day the gates ran on 3.14, while the
  image runs 3.13 (`deploy/docker/Dockerfile`).
- **New:** `.python-version` names `3.13`. `uv` reads it locally and in CI, so the tests run on
  the interpreter production runs.
- **What stays:** `requires-python = ">=3.13"` in `pyproject.toml`. Moving the image and the pin
  to a newer version is one change of two lines, made together.

## 2. The evidence

- The failing job of pull request #167: `uv sync` chose CPython 3.15.0 and stopped with
  "`psycopg-binary` (v3.3.5) only has wheels with the following Python ABI tags: `cp313`,
  `cp314`".
- With the pin, `uv sync --all-extras` installs on 3.13.7 and `make gates` passes.

## 3. What was considered

- **Pinning 3.14**, the version the gates used until yesterday. Not taken: it tests an
  interpreter production does not run.
- **An upper bound in `requires-python`.** Not taken: it says what the package supports, not
  what the gates run on, and would refuse a newer interpreter that works.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The tests now cover the
interpreter the image runs; no gate checks anything different.
