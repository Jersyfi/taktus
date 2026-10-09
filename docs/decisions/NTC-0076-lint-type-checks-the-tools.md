# NTC-0076 — Lint type-checks the tools

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** [#143](https://github.com/Jersyfi/taktus/pull/143), for issue #142

## 1. What was decided

`make lint` type-checks the repository's Python tools under `tools/` with the same strict
`mypy` settings as the product.

- **Old:** `[tool.mypy]` in `pyproject.toml` named the package `taktus` only. The gates under
  `tools/` were never type-checked. `tools/check_decisions.py` carried two errors no gate saw.
- **New:** `[tool.mypy]` names the files `src/taktus` and `tools`, under `strict = true`.
  `make lint` runs `mypy` with no arguments, so it checks both.
- **The two errors are fixed** without changing what the gate checks. In the notice checks a
  variable `body` was first bound to a section's text and then reused for a lookup that may
  find nothing. The two lookups now have their own names, `gate_body` and `unlisted_body`.
- **A test holds the coverage** (`tests/tools/test_lint_tools.py`). It fails when a tool is
  outside the configured files or `strict` is off. It runs `mypy` as `make lint` does, with
  `tools/gate.py` replaced by a copy carrying a wrong annotation, and expects the error.
- **The shell scripts under `tools/` stay outside the check.** Issue #142 bounds it so.

## 2. The evidence

- Issue #142 names the verification: `make lint` checks `tools/*.py`, `check_decisions.py`
  passes, and a deliberately wrong annotation in a tool makes `make lint` fail.
- Before the change, `mypy --strict tools/*.py` reported exactly the two errors in
  `tools/check_decisions.py` and nothing in the other nine tools.
- After it, `make lint` reports no issue in 239 source files: the 229 modules of `taktus` it
  checked before and the ten tools.
- With the old configuration restored, both tests of `tests/tools/test_lint_tools.py` fail.
  With the new one, both pass.

## 3. What was considered

- **A second `mypy` call in the `lint` target, naming `tools/`.** Not taken: the coverage
  would live in the Makefile and a bare `uv run mypy` would check less than `make lint`. One
  configuration keeps both the same.
- **`packages` and `files` side by side.** Not possible: `mypy` accepts only one of the two.
  `files = ["src/taktus", "tools"]` checks the same modules of `taktus` as `packages` did.
- **A milder setting for the tools.** Not taken: the issue asks for the product's check, and
  the tools already passed it except for the two errors.
- **Stating the wrong-annotation check by hand in the pull request.** Not taken: the test costs
  a few seconds and keeps the check true when the configuration changes later.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." `make lint` now covers the
tools. No gate checks anything different: the fix in `check_decisions.py` renames two
variables. `tests/README.md` and `tools/README.md` say the same.
