# NTC-0207 — A registered version never changes

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-13
**Raised in:** the pull request for issue #377

## 1. What was decided

1. **Registration refuses a version that exists with another content.** A bundle whose
   identifier and version are stored already, with a different document, is refused: "a
   registered version never changes: give the bundle a new version". Who registered it and
   why are not part of the comparison.
2. **The same content again is the stored version.** Nothing is stored or recorded anew.
3. **P-03's bundle is version 7.** #367 changed it under version 6.

## 2. The evidence

- 2026-10-13, the installed instance: after #367 reached it in `rc.10`, `taktusctl submit` of
  P-03's bundle stored the new content as `p03-implementation@6`. The stored document now holds
  #367's acceptance criterion; the runs `run_0fe0ff759342c538f0fd` and
  `run_fd221e54dff23b6ad891`, which ran the earlier content, name the same version. The earlier
  content is in git at commit a67a040.
- `tests/components/process/test_bundle_parsing.py`
  `test_a_registered_version_never_changes`.

## 3. What was considered

- **Store every registration as a new version automatically.** The bundle's version is what
  people and records name; a version number the system invents would not match the file.
  Not taken.
- **Accept a change that only adds text to an acceptance criterion.** Any change of the work
  changes what a run of the version does. Not taken.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #377. It holds what CLAUDE.md §9 already requires: no process
version history is deleted without asking, and overwriting a version deletes the one it
replaces. Restoring the instance's stored version 6 to what it was is a restore and stays the
owner's.
