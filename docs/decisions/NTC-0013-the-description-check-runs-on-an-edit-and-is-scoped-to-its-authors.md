# NTC-0013 — The description check runs on an edit, and is scoped to its authors

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-01
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51)

## 1. What was decided

Two changes to the check that reads a pull request's description: whether it has the four
sections a reviewer can act on without the diff, the decisions it raises, and the list of what
is needed from the owner.

- **It runs when a description is edited.** **Old:** it ran when a pull request was opened,
  reopened or pushed to. Correcting a description therefore could not turn the check green
  without a new push; closing and reopening the pull request was the workaround. **New:** it runs
  in a workflow of its own, `description`, on every event that can change what it reads: opened,
  reopened, a push, an edit of the description, and a change of the draft state. The register,
  ADR and status gates on the branch stay in `ci`, unchanged.
- **It asks the shape of the authors it is for.** **Old:** every pull request was held to the
  shape, including a dependency bot's, whose description is written by the bot and will never
  carry the sections. Every such pull request failed for ever. **New:** a description written by a
  dependency bot (`dependabot[bot]`) is not held to the four sections, the decisions line or the
  owner list; it carries its own explanation of what it changes. Every code gate, the register and
  the status gates still run on its pull requests. A pull request a session or Taktus writes is
  held to the shape exactly as before. When the repository-hygiene process P-10 runs, Taktus
  writes these descriptions itself, in the required shape.

This scopes a gate to its purpose, which is that the owner understands what he is reviewing. It
does not weaken it: what a session or Taktus writes is checked as before, on more events than
before.

## 2. The evidence

- 2026-10-01, every open pull request was red on this check alone, each for this reason: #51 was
  checked against the placeholder it was opened with, and a re-run replays the original event;
  #38 was checked against its description before the regenerated owner list was posted; #47,
  a dependency update, has a bot's description. Every code gate on all three was green.
- The workflow's trigger before the change: `pull_request:` with no types, which GitHub reads as
  opened, synchronize and reopened — not edited.
- The tests: `tests/tools/test_description_and_status.py` — a bot's description passes both tools,
  the same text from a person or with no author fails, and both tools name the same bots.

## 3. What was considered

- **Adding `edited` to the `ci` workflow.** Rejected: every edit of a description would re-run the
  five-minute code gates.
- **Skipping the check for every bot.** Rejected: only a dependency bot writes its own
  explanation of a change; any other bot is held to the shape, and a new bot is added by name.
- **Asking the bot for the sections** through a configuration. Rejected: the bot writes no
  sections the repository asks of it.

## 4. Which entry permits it

M2.4: a change of what the repository's checks do, inside the agreed scope of keeping the gates
true (CLAUDE.md §11, point 11), breaking no contract and moving no limit, level or public
statement. The owner directed that it be recorded as a notice that scopes a gate to its purpose.
