# NTC-0003 — The first run's credential variables renamed

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-09-23
**Raised in:** [#23](https://github.com/Jersyfi/taktus/pull/23)

## 1. What was decided

`tools/first_run.sh` reads the paths of its two credential files under different variable
names than before. What was `REPOSITORY_TOKEN_FILE` is now
`TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE`; what was `CODING_AGENT_API_KEY_FILE` is now
`TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE`; what was `CODING_AGENT_SESSION_FILE` is now
`TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE`. The script refuses to start naming the new
variable when it is absent, as it always did.

Nothing else about the script changed: the same files hold the same values, the token still
reaches the connector process and nothing else, the agent's credential still reaches the worker
process and nothing else, and no value is ever an argument.

Why the old names went: they broke the one pattern the repository states for a secret's file,
and the coding agent's key had two names for one file. The reasoning is DEC-0018; this notice
records the half of it that an operator can feel.

## 2. The evidence

- CLAUDE.md §9 states the pattern `TAKTUS_<KEY>_FILE`; `CREDENTIALS.md` states
  `TAKTUS_CREDENTIAL_<NAME>_FILE` for a credential; the environment configuration adapter
  derives that name from the configuration key
  (`src/taktus/adapters/driven/configuration/environment.py`, `FILE_SUFFIX`).
- Before this change, six credential file variables existed in the repository and three of
  them followed the pattern: `TAKTUS_DATABASE_URL_FILE`, `TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE`,
  `TAKTUS_OTLP_HEADERS_FILE`. The other three were the script's.
- The coding agent's key appeared under two names in one register: `CREDENTIALS.md` named
  `TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE` for a launched unit and
  `CODING_AGENT_API_KEY_FILE` for the script, in the same row.
- Nobody has the old names in a file: `.env` did not exist in any checkout before this pull
  request, because the credentials the script needs were provided on 2026-09-22 and wired
  here. `grep` over the tree finds no remaining use outside the historical records DEC-0016
  and this one.

## 3. What was considered

- **Leave the names as they were and document the exception.** Rejected: the exception would
  have to be repeated in every needs request, and the two names for the coding agent's key
  would stay two names. A rule with a documented exception is two rules.
- **Move the other way — drop the prefix everywhere.** Rejected: the prefix is not decoration.
  It is how the environment configuration adapter finds a configuration key's file, and
  `TAKTUS_` keeps Taktus's variables apart from everything else in a shell that starts a
  container. Dropping it would change the composition root, the execution adapter and the
  compose files to fix a script.
- **Accept both names in the script, old and new.** Rejected: two accepted names is the defect
  with a deprecation period attached, for a script that no deployment has ever run and whose
  variables nobody has written down yet. The cost of the rename today is one line in a
  record; in six months it would be a migration note.

## 4. Which entry permits it

Entry M2.4 of `docs/decisions/anchors.taktus.md`: "**A change of what the software does, made
inside an agreed scope**, that breaks no contract, moves no limit or autonomy level and says
nothing public." Wiring the three provided credentials is the agreed scope, and reading their
paths is what the script does inside it. No contract carries these names: the worker contract
and the connector contract carry the *credential's* name (`CODING_AGENT_API_KEY`,
`REPOSITORY_TOKEN`), which is unchanged, not the name of the variable that points at the file.
No limit moves, no autonomy level moves, and nothing published under the project's name says
anything about them, so M3.5, M3.10, M3.9 and M3.7 do not apply.
