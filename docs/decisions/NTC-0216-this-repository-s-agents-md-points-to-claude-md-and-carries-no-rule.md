# NTC-0216 — This repository's AGENTS.md points to CLAUDE.md and carries no rule

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-18
**Raised in:** issue [#407](https://github.com/Jersyfi/taktus/issues/407), in the pull request that closes it
**How it follows:** Principle 13 asks for the open format over a product's own, and DEC-0195 (W6) asks Taktus to use the formats its field agreed on: for a repository's rules for coding agents, that is `AGENTS.md`. CLAUDE.md's first standing order asks that a change of how work is done here is carried in the doctrine in the same pull request, and the brief of #407 asks that the doctrine is not shortened or weakened. Two options were both consistent with these sources: a pointer in `AGENTS.md`, or the doctrine moved into `AGENTS.md` with `CLAUDE.md` importing it. The pointer was taken. It is as strict in substance — every agent reaches the whole doctrine through the open file, and the doctrine exists once — and it needs less ceremony: no file that names the doctrine changes.

## 1. What was decided

This repository gains an `AGENTS.md` of a few lines. It says that the rules are `CLAUDE.md`, that
they bind every agent and every person, and that they must be read whole. It carries no rule of
its own. `CLAUDE.md` §9 gains the rule that a rule goes into `CLAUDE.md`, never into `AGENTS.md`.
The doctrine itself is unchanged (ADR-0113 §5).

## 2. The evidence

- `tests/workers/test_coding_worker_rules.py`
  `test_this_repository_s_agents_md_points_to_its_doctrine_and_is_handed_over`: the file links
  `CLAUDE.md`, stays a pointer, and is what both coding workers hand their agent here.
- More than a hundred tracked files name `CLAUDE.md`. `tools/check_vision.py` reads its §5. The
  migrations name it in texts that are never changed.

## 3. What was considered

- **The doctrine moved into `AGENTS.md`, and `CLAUDE.md` importing it.** The doctrine would sit
  in the open file. Rejected for now: every reference to a section of `CLAUDE.md` would point at
  an import line, the gates would read another file, and the migrations could not follow. It can
  be done whole in a pull request of its own.
- **No `AGENTS.md`.** A coding agent other than the first coding worker's would find no rules.
  Rejected: principle 13.
- **A copy of the doctrine in `AGENTS.md`.** Two copies drift apart, and the first coding
  worker's agent would read both at every call (#511). Rejected.

## 4. Which entry permits it

No entry of modes 3 or 4 names the files through which agents find this repository's rules.
M4.5 is the vision layer, which this does not touch. No entry of mode 2 names it either, so M2.6
applies.

## 5. The entry it proposes

M1.25: *the entry points through which a coding agent finds this repository's doctrine*, as long
as the doctrine itself stays whole and unchanged. Moving the doctrine to another file stays a
change of how work is done here, carried in the doctrine in the same pull request.
