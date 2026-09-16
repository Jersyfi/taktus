# DEC-0006 — The gates assumed an installed environment

**Category:** DEFECT
**Raised in:** [#5](https://github.com/Jersyfi/taktus/pull/5), which adds the first slice of the control plane
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The repository has one command that runs every check a change must pass: `make gates`. Its
documentation said that this command needs two programs on the machine — `uv`, which manages
the Python environment, and `gitleaks`, which scans for secrets — "and nothing else". On a fresh
copy of the repository the command failed at once with "Failed to spawn: ruff". The checker
`ruff` lives inside the project's own Python environment, which nobody had created yet; the
documentation assumed that whoever ran the gates had run `make install` first, and nothing said
so.

A second command, `make doctor`, exists to say what is missing before anything fails. On the
same fresh copy it reported "every required tool is present". It checked only the two programs
on the machine, not the environment the gates actually run in, so the one thing that was
missing was the one thing it did not look at.

A third target, `make generate`, referred to a script that did not exist and would have failed
with a missing-file error.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies: no gate is weakened, nothing public changes. This
is row D6 of §2 — the repository's documents said something that was not true of its tooling —
and is corrected and recorded in the same pull request. The pull request that added the
tooling, [#4](https://github.com/Jersyfi/taktus/pull/4), named this the rule: a gate that cannot
run says why, and an unclear message is a defect.

## 3. What you must decide

Nothing. The record exists so that the next tooling change is measured against the same
standard: a gate ensures its own environment, and a doctor checks what the gates invoke.

## 4. What you need to know to decide

- **Project environment.** The directory (`.venv`) in which `uv` installs the project and the
  tools it needs — `ruff`, `mypy`, `pytest`, `lint-imports`, `taktusctl`. The gates run these
  tools from there, never from the machine's own installation.
- **`make install`.** The target that creates that environment. Until now it had to be run by
  hand before the gates; nothing in the gates depended on it.
- **Why this is a defect and not a decision.** Whether a gate installs its own environment
  changes nothing about what the gate checks. It changes whether a fresh copy is green in one
  command, which the documentation already claimed.

## 5. Options

None for the owner. What the session did: every make target that runs a tool from the project
environment now depends on a target `env`, which runs `uv sync` once when the environment is
absent or older than `pyproject.toml` or `uv.lock`, so that a fresh clone is green in one
command and a warm one pays nothing; `make doctor` reports two levels — the programs on the
machine and the tools in the project environment — and names which is incomplete and the
command that completes it; `make generate` runs a script that states what is generated (nothing
yet) instead of failing.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0006" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-16
**What was wrong:** `tools/README.md` said `make gates` needs `uv` and `gitleaks` "and nothing
else" and that `make doctor` says what is missing; on a fresh checkout `make gates` failed with
"Failed to spawn: ruff" because the project environment had never been created, and `make
doctor` reported every required tool present while `ruff`, `mypy` and the other tools the gates
invoke were missing. `make generate` referred to a script that did not exist.
**Why it was wrong:** the gates assumed that `make install` had been run and nothing checked
or said so; the doctor checked the machine and not the environment the gates use.
**What it now says:** `Makefile` — every target that runs a tool from the project environment
depends on `env`, which syncs the environment when it is absent or out of date; `tools/preflight.sh
--doctor` reports the system tools and the project environment as two levels and says which is
incomplete; `tools/generate.py` exists and says what is generated; `tools/README.md` states all
three.
**What changed in substance:** nothing a gate checks. A fresh clone is green in one command, as
the documentation had claimed.
**Recorded in:** [#5](https://github.com/Jersyfi/taktus/pull/5)
