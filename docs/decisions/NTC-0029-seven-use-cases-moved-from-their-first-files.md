# NTC-0029 — Seven use cases moved from their first files

**Mode entry:** M2.1
**Kind:** restructuring
**Decided:** 2026-10-08
**Raised in:** [#61](https://github.com/Jersyfi/taktus/issues/61)

## 1. What was decided

Seven use cases written before the use case format existed are now files in the format, in the
folder of the component that owns them:

| Use case | Was in | Is now |
|---|---|---|
| UC-4.6 self-healing within the frame | a state of `docs/architecture/control-plane.md` §5.2 | `docs/usecases/run/` |
| UC-4.11 error window and impact analysis | `docs/usecases/UC-4-result-defects.md` | `docs/usecases/run/` |
| UC-4.12 remediation plan | `docs/usecases/UC-4-result-defects.md` | `docs/usecases/run/` |
| UC-6.8 incident and incident report | `docs/usecases/UC-4-result-defects.md` | `docs/usecases/governance/` |
| UC-7.2 emergency stop | `docs/usecases/UC-4-result-defects.md` | `docs/usecases/governance/` |
| UC-4.13 working out how a step becomes exact | `docs/usecases/UC-4-exactness-statement.md` | `docs/usecases/process/` |
| UC-6.9 the exactness statement | `docs/usecases/UC-4-exactness-statement.md` | `docs/usecases/process/` |

The two first files were removed once nothing was left in them. The links that pointed at them —
in ADR-0014, `docs/architecture/methods.md`, `docs/usecases/run/UC-4.10-deviation-detection.md` and
the table "Not yet in this format" of `docs/usecases/README.md` — point at the new files, and the
table became a paragraph saying where each case went.

## 2. The evidence

- The five parts of the earlier shape map onto the format one to one, as `docs/usecases/README.md`
  already said: the situation and what Taktus does are section 1, what it never does and how it is
  proven are section 2, what it needs is section 4. Every requirement of the first texts is in the
  new files in that mapping; the wording was shortened in places, and the first texts stay readable
  in the repository's history.
- The folders follow ADR-0029's table for UC-6.8 (`governance`) and UC-6.9 (`process`), and the
  component that owns the code for the others: the provenance chain and the run engine for UC-4.6,
  UC-4.11 and UC-4.12, the anchors and the stop rule for UC-7.2, the process version for UC-4.13.
- ADR-0014's change is the path of one link; its digest was recorded again in UC-4.1 after reading
  it.
- `make gate-usecases` is green with the seven files.

## 3. What was considered

- **Leaving the first files as pointers**, as step 1 did for UC-4.10. Rejected: with all their cases
  moved, a file of pointers is a second place to keep current, and `MIGRATION.md` deletes such
  files at the end anyway.
- **Moving without a notice.** Rejected: two files were removed and an accepted ADR's text changed,
  and a reader of the register should find when and why.

## 4. Which entry permits it

M2.1, *"Documentation restructuring without changing what the documents say."* The move changes no
requirement. Two changes of what a moved use case requires were made in the same pull request and
are recorded separately: the restoration of NTC-0030 under M2.7, and the incident naming a role in
UC-4.12, which is the owner's and is asked in DEC-0069 under M3.15.
