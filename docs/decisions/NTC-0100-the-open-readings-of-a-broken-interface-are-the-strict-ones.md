# NTC-0100 — A broken interface's open readings, strictly

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** issue [#100](https://github.com/Jersyfi/taktus/issues/100), in the pull request that closes it
**How it follows:** Issue #100 and DEC-0058 state what must hold and leave five readings open. Each is decided by the source that governs the same question elsewhere: the connector contract's own vocabulary (`contracts/connector/v1` §5 and §6, which keeps source-system permissions in force and calls `unavailable` the cause a retry remedies), ADR-0024 §3 (the engine retries nothing; a retry is a resume), ADR-0023 (an automatic act is decided by a rule over what was recorded), ADR-0030 (a rehearsal runs on a configuration altered on purpose) and ADR-0028 (a report states the date it is needed by). Where two readings were both consistent, the one taken is the stricter in substance — the owner hears of an interface that stopped, including an outage that a retry did not pass — and the one with less ceremony: no new store, one report per broken interface, no message per call.

## 1. What was decided

1. **What the contract does not foresee** is three causes: the connector answered outside its
   contract, the service refused the authentication, or it answered a status or a shape the
   connector does not foresee (`unexpected`, a cause added for this). `forbidden`, `not_found`,
   `invalid` and `conflict` are the service answering about the input or the state, and never
   count.
2. **A transient failure** — `unavailable`, an answer that did not arrive, a connector that did not
   answer — counts only once a retry of the same step failed too. One that a retry resolved never
   counts. An outage that persists across a retry is reported: the interface stopped working, which
   is what DEC-0058 asks Taktus to notice.
3. **A rehearsal's calls** are left out: it runs on a configuration altered on purpose, such as the
   removal test's.
4. **The date a report is needed by** is the day it is raised: the runs it held up stand still now.
5. **A broken interface closes** when the owner answered its report that it is done. A call that
   fails after that opens a new one; before that, every failed call adds to it and nothing is said
   again.

## 2. The evidence

- Issue #100: "calls that fail in a way the connector's contract does not foresee — an unexpected
  shape, an authentication refused, a status that should not occur"; "a transient failure that a
  retry resolves raises nothing".
- `contracts/connector/v1` §5: "Source-system permissions remain in force"; §6: `unavailable` is
  retryable with the same key.
- ADR-0024 §3 and the engine's own description: the engine retries nothing on its own.
- `tests/adapters/connectors/test_broken_interfaces.py` and
  `tests/components/reporting/test_broken_interfaces.py` hold each reading.

## 3. What was considered

- **`forbidden` counts.** Rejected: a process that asks for what its identity may not do is the
  contract working as written.
- **Transient failures never count.** Rejected: a service down for a day would never reach the
  owner, though it stopped working.
- **A transient failure counts at once, or after a waiting time.** Rejected: the first pages the
  owner for a moment's outage; the second is a race between the look and the retry.
- **The date a week ahead.** Rejected: nothing waits a week for a broken interface; the runs it
  holds stand still today.

## 4. Which entry permits it

None of modes 3 and 4 names which failures of a call speak about its interface, or how a report of
one is dated. What issue #100 requires is unchanged, and no limit or level moves. No entry of mode
2 names it. M2.6 applies: decided in the direction of the sources above.

## 5. The entry it proposes

**M1.19** — *Reading a failed call*: which causes of a failed call speak about its interface, and
when a transient one counts, follow the connector contract's vocabulary and a failed retry; a
cause the contract adds later is placed in the same two lists by the same reading. Mode 1, because
it applies the contract's own meaning of each cause without choosing anything new.
