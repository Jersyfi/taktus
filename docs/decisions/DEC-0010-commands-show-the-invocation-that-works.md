# DEC-0010 — Every command shows the invocation that works

**Category:** DEFECT
**Raised in:** [#9](https://github.com/Jersyfi/taktus/pull/9), which adds the daemon and its roles
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The command line of Taktus, `taktusctl`, and every module of the package are installed into the
project's own environment — a directory the tool `uv` manages — and not onto the machine's path.
A command written as `taktusctl run` therefore does not work as written from a checkout; the
invocation that works is `uv run taktusctl run`. The same holds for a module started with
`python -m`: from a checkout it is `uv run python -m`.

Most places in the repository showed the working form. Two did not: the reference connector's
README and the module's own docstring showed `python -m taktus.adapters.driven.connectors.github`
bare, and the control plane's architecture document referred to the resume command bare. A reader
who copies the command gets "module not found" and has to know the environment to understand why.
Nothing in the documentation said that this is the rule.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies. A document showed a command that does not work
as shown, which is row D6 of §2 — corrected and recorded here — and the rule that prevents the
next one is row D4, the wording of an already-decided thing, recorded in the conventions.

## 3. What you must decide

Nothing. The record exists so that the rule has one place — the conventions table of
`docs/architecture/project-structure.md` — and every command in the repository is measured
against it.

## 4. What you need to know to decide

- **Project environment.** The directory `uv` creates for the project (`.venv`), holding the
  package, its dependencies and its console scripts. Everything in it runs through `uv run`.
- **On the path.** A program the machine finds by name alone: `make`, `docker`, `python3`. The
  reference worker under `workers/script/` is a single file that needs nothing installed and
  is run with the machine's `python3`; that invocation stays bare.
- **Why this is a defect and not a decision.** Which environment the package lives in was
  decided with the tooling (DEC-0006). A command that contradicts it is wrong, not a choice.

## 5. Options

None for the owner. What the session did: corrected the three invocations; added the rule to
the conventions table — every invocation shown is the one that works from a checkout, `uv run`
for anything in the project environment, bare only for what is on the machine's path — so that
the next command is written against it.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0010" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-17
**What was wrong:** `src/taktus/adapters/driven/connectors/github/README.md` and the module's
docstring showed `python -m taktus.adapters.driven.connectors.github` without `uv run`;
`docs/architecture/control-plane.md` §5.1 referred to `taktusctl run --resume` bare; no
convention said which form a command takes.
**Why it was wrong:** the package and its console scripts live in the project environment and
not on the machine's path, so the commands do not work as shown.
**What it now says:** the three places show `uv run`; `docs/architecture/project-structure.md`
§4 carries the row *Commands in documentation*: every invocation shown is the one that works
from a checkout.
**What changed in substance:** nothing the software does.
**Recorded in:** [#9](https://github.com/Jersyfi/taktus/pull/9)
