# NTC-0005 — The status date check is removed

**Mode entry:** M2.3
**Kind:** gate-weakened
**Decided:** 2026-09-29
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46)

## 1. What was decided

`make gate-status` no longer compares a date in `docs/status.md` with the newest record of the
decision register, because the file no longer carries a date (DEC-0027). In its place the gate
fails a status file that carries an `As of` line or a running *Decided since* list at all.

## 2. The evidence

- The check read `**As of:**` and failed when it was older than the newest `Decided`,
  `Corrected`, `Recorded` or `Provided` date of any file under `docs/decisions/`
  (`tools/check_status.py`, `check_date`, as of `main` at 129d865).
- Every such date is written in a file under `docs/decisions/`. The freshness check of the same
  gate fails any pull request that changes a file under `docs/decisions/` without changing
  `docs/status.md` (`check_freshness`, the pattern `STATE`). A record that the date check would
  have caught is therefore caught by the freshness check in the same pull request.
- The one case the freshness check does not see is a record whose date is later than the pull
  request that adds it — a date in the future. The date check would not have caught that either:
  the status would simply have been dated in the future too.

## 3. What was considered

- **Keep the check with a date the gate writes.** Rejected: a written date is still a line every
  branch changes, and the conflict DEC-0027 removes comes back.
- **Keep the check and the date by hand.** Rejected: it is the cause of the conflicts.

## 4. Which entry permits it

M2.3 of `docs/decisions/anchors.taktus.md`: *"Weakening or removing a gate, only where it is
demonstrated that the gate has no value."* A check of a gate is removed; no entry of mode 3 or 4
concerns the status gate, and the demonstration is section 5.

## 5. Why the gate had no value

The gate is `make gate-status` (`tools/check_status.py`); the check removed is its date check,
`check_date`. It looked at the `As of` date of `docs/status.md` and at the newest date of the
register. It would have caught a status file not updated after a decision was recorded. Every
decision is recorded by adding or changing a file under `docs/decisions/`, and the freshness check
of the same gate fails that pull request unless `docs/status.md` changes in it too — so the date
check could only ever fail where the freshness check already failed: its value was entirely
duplicated, by construction, not by observation. What it added was the date line, and with it the
conflict: pull request #38 conflicts with `main` in the file's header, on the date line and on the
line DEC-0026 already removed. What it caught is caught by the freshness check.
