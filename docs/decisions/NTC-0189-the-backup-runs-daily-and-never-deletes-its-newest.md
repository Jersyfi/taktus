# NTC-0189 — The backup runs daily and never deletes its newest

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-11
**Raised in:** issue [#67](https://github.com/Jersyfi/taktus/issues/67), in the pull request that closes it
**How it follows:** DEC-0058 fixes how long a backup is kept (30 days, configurable) and that Taktus keeps the retention itself; it says nothing about how often a backup is taken, nor what the retention does when no new backup arrives. ADR-0013 C asks for a restore path that works when Taktus does not. Where two choices were both consistent with these, the stricter in substance was taken: a backup every day rather than less often, and a retention that can never leave the store empty.

## 1. What was decided

1. **The schedule is daily**, at 03:17 UTC, as the chart's default (`backup.schedule`); an
   operator sets another.
2. **The newest backup is never deleted**, whatever the retention says. A retention of 0 keeps
   one backup; a schedule that stopped for longer than the retention leaves the last backup
   there instead of deleting everything.
3. **An object the backup did not write is never deleted**: only names of its own form are
   candidates.
4. **A run whose backup failed deletes nothing.**

## 2. The evidence

- `tests/deploy/test_backup_retention.py`: retention 0, 1 and 30 days; the newest kept however
  old; a foreign object untouched; a negative retention refused.
- `tests/deploy/test_backup_restore.py`: the retention kept through a directory and through an S3
  interface; an earlier backup of 2020 deleted and an unrelated object kept.
- `deploy/k8s/chart/values.yaml`, `backup.schedule`; `tests/governance/test_chart.py`.

## 3. What was considered

- **Weekly**, the cadence of the removal test. Rejected: a week of the ledger lost with the node.
- **Hourly.** Possible later; a daily dump is what ADR-0013 C asks for, and each dump is the
  whole database.
- **The retention applied strictly**, an empty store allowed. Rejected: a store emptied by its own
  retention is the failure the backup exists to prevent.

## 4. Which entry permits it

No entry of modes 3 or 4 names how often a backup runs. M3.10 names limits — a budget, a quota,
a resource bound — and the retention is one, which the owner set in DEC-0058 and this keeps. No
entry of mode 2 names it either, so M2.6 applies.

## 5. The entry it proposes

**M1.21** — *How the operation keeps its safety copies*: the schedule of a backup and the rules
that keep a retention from removing the last copy, within the retention the owner set. Mode 1,
because the owner set the retention; changing the retention stays M3.10.
