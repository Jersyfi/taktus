# DEC-0044 — The licence

**Category:** NON-BLOCKING
**Mode entry:** M4.1
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52), from the audit of the register, which found ADR-0012 open with no request, no issue and no date
**Issue:** [#56](https://github.com/Jersyfi/taktus/issues/56)
**Needed by:** before 1.0.0, and before the first contribution from outside is accepted
**Provisional answer:** none is chosen for you: this is your own question (mode 4). Until you answer, ADR-0012's reservation holds — the repository is public, all rights are reserved, and no contribution from outside is accepted.

## 1. What this is about

Taktus's source is public, but nobody may use it: `LICENSE` reserves all rights. That was
decided as the state until you choose a licence (ADR-0012). `NOTICE` states the intent — Fair
Source or Source Available before version 1.0.0, with the contracts and the reference adapters
licensed more permissively than the control plane — and leaves the model open. Until now the
open question had no record, no issue and no date, so nothing would have reminded anyone before
1.0.0 or before an outside contribution arrived.

This request tracks it. It does not recommend: the licence is your own question, and the
session's part is to supply what you need to decide.

## 2. Why you are being asked

Entry M4.1 of `docs/decisions/anchors.taktus.md`: "The licence (ADR-0012)." Mode 4: the owner
decides, the session supplies data.

**Sources checked:** the vision (`docs/vision/`) names freedom instead of vendor lock-in
(principle 13) and European values and sovereignty (principle 11), which bound the choice but do
not make it; ADR-0012 records the question as open and the owner's to decide, and ADR-0010 ties
the price to an accounting basis still being calibrated; the anchor pages place the licence in
mode 4 on both `anchors.md` and `anchors.taktus.md`; the register holds no decision on it. None
of them answers it, and none may: it is the owner's own question.

## 3. What you must decide

Under which licence Taktus is published — and, as ADR-0012 recommends whatever the model, whether
the contracts and the reference adapters carry a more permissive licence than the control plane.

## 4. What you need to know to decide

- **What holds until then.** All rights reserved; no outside contribution is accepted. An
  accepted outside contribution belongs to its author under unclear terms and would bind any
  later licence change to their agreement (ADR-0012).
- **What every option needs before outside contributions open:** a contributor agreement, so
  that a contribution can be published under the licence you choose and under a later one.
- **The split NOTICE announces.** The contracts and reference adapters permissive, so that
  anyone may build an adapter and pass it on; without that, the promise of no lock-in is not
  credible, because the alternative may not legally be built (ADR-0012, principle 13).
- **What depends on it.** The price (M4.2) and the accounting basis (M4.3, ADR-0010) are your
  own questions too; a licence that allows free commercial use leaves less to charge for, one
  that forbids it more.
- **When it is due.** Before 1.0.0, which is the first release meant for others to run; and
  before the first contribution from outside is accepted, whichever comes first. There is no
  earlier date: nothing built before then depends on it.

## 5. Options

### Option A — Fair Source for the control plane, permissive for the contracts

- **Meaning:** the control plane's source may be read, run and changed, with commercial use
  restricted for a fixed period, after which each version becomes open source; the contracts and
  reference adapters under a permissive open-source licence. This is the intent `NOTICE` states.
- **Consequence:** competitors cannot sell Taktus as their own during the period; everyone may
  self-host, and every version opens in time.
- **Effort:** choosing the licence texts, a contributor agreement, updating `LICENSE` and
  `NOTICE` and the files' headers.
- **Reversibility:** a version once published under a licence stays under it; later versions may
  change.

### Option B — Source Available without conversion, permissive for the contracts

- **Meaning:** the control plane's source may be read and self-hosted under conditions you set,
  without a date at which it becomes open source; the contracts and reference adapters
  permissive.
- **Consequence:** the most control over commercial use; the least for those who rely on Taktus
  staying available if the project changes course — the takeover promise (ADR-0013 B) then rests
  on the licence's terms.
- **Effort:** as Option A.
- **Reversibility:** as Option A.

### Option C — an open-source licence throughout

- **Meaning:** the control plane under an open-source licence — a copyleft one keeps changes to a
  hosted service public, a permissive one does not — and the contracts permissive.
- **Consequence:** the widest use and contribution; commercial use cannot be restricted, so the
  price must rest on something other than the right to use the code.
- **Effort:** as Option A.
- **Reversibility:** a version published open source stays open source.

## 6. What is blocked

Nothing now. At 1.0.0, or when the first outside contribution would be accepted, the release or
the contribution waits for this answer.

## 7. How to answer

"DEC-0044: Option A." — or B, or C — with the licence texts you choose, or any model of your own,
in issue [#56](https://github.com/Jersyfi/taktus/issues/56). A free-text answer is read back as an
interpretation and confirmed before it is acted on.
