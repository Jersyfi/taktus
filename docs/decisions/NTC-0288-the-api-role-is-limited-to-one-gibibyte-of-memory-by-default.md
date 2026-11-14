# NTC-0288 — The `api` role is limited to one gibibyte of memory by default

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-14
**Raised in:** branch `area/speed` (package F, concept mode, DEC-0239)
**How it follows:** ADR-0013 A requires that Taktus runs without interruption. A process that
reaches its memory limit is killed by the platform, and every stream and request it holds ends.
The analysis of 2026-11-14 measured the `api` role's process at 782 MB, and this session at
816 MB, for five full reads of 3,000 runs at once, against the chart's limit of 512 MiB. M3.10
keeps a limit with the owner where it bounds what work may spend (ADR-0005: a budget, a quota, a
step's compute bound, a margin); a pod's memory limit bounds no work and spends nothing, it is
the size of the container the role runs in. Strict in substance: the default holds the measured
peak; sparing in ceremony: an operator who sets their own value keeps it.

## 1. What was decided

`deploy/k8s/chart/values.yaml`: the `api` role requests 384 MiB (was 256 MiB) and is limited to
1 GiB (was 512 MiB). The `small` profile, every role in one process, is limited to 1 GiB (was
768 MiB). The other roles are unchanged.

## 2. The evidence

- `bench3.py` of the analysis, rerun on 2026-11-14 before the change: five full reads of 3,000
  runs at once, peak resident memory 816 MB.
- `tests/integration/test_run_listing_at_scale.py` (ADR-0320 §1): the release before peaked at
  1,221 MB with five readers opening its start page; after ADR-0317 to ADR-0319, 249 MB. Views
  that still read every run remain (ADR-0320 *Where this promise ends*), so the limit holds the
  first figure, not the last.

## 3. What was considered

- **Keep 512 MiB, since the start page no longer reads every run.** Rejected: other views still
  do, and the measured peak of five of them at once exceeds it.
- **Raise only the `small` profile.** Rejected: the `standard` profile's `api` role serves the
  same requests.

## 4. Which entry permits it

M2.6, following ADR-0013 A. The owner may overrule it in the pull request.

## 5. The entry it proposes

M1.27 — **The resources a role's container requests and is limited to** in the shipped chart, as
long as the default holds a peak measured and stated in an ADR; a limit on what work may spend
stays M3.10.
