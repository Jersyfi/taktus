# DEC-0226 — What the roadmap asks of outside systems the project does not use

**Category:** NON-BLOCKING
**Mode entry:** M3.6 and M3.15 (what holds a release back), the roadmap
**Raised in:** the session of 2026-11-03, from DEC-0225
**Issue:** [#669](https://github.com/Jersyfi/taktus/issues/669)
**Needed by:** before `1.0.0-beta` is prepared
**Provisional answer:** Option A, marked in `docs/status.md`. Nothing is built on it until you answer.

## 1. What this is about

You decided in DEC-0225 that the project tests live only what it uses itself: Anthropic, the
repository service, the chat workspace, the password manager, its own cluster. Three items of the
roadmap still ask the project's own instance to reach systems outside that list:

1. **The first beta condition:** "payment reconciliation or the cost watcher of UC-03 runs on
   Taktus's own instance against the real service". The project has no payments. Its Anthropic
   account is one for an individual, which cannot read its costs through an API.
2. **The `1.0.0` removal condition:** S-01 green "in an installation with an alternative for
   every capability a reference adapter serves". The only alternative coding agent is at a
   vendor the project does not use (NEED-0022, closed by DEC-0225).
3. **The accelerator for the ML bench** (NEED-0023, #210). The project trains nothing on an
   accelerator for its own operation.

## 2. Why you are being asked

The roadmap and what holds a release back are yours (M3.6, M3.15). A session may not change a
release condition, nor drop one without a decision.

**Sources checked:** `docs/vision/` (principle 13, freedom instead of lock-in, and the non-goals), the ADRs on connectors (ADR-0009, ADR-0150), both anchor pages (`docs/decisions/anchors.md`, `anchors.taktus.md`: M3.6 and M3.15 keep release conditions with you), `docs/roadmap.md` ("The road to 1.0.0"), DEC-0222 (the beta first),
DEC-0201 (the first customer runs Taktus himself and reports findings), DEC-0225, UC-03,
UC-6.12. None of them says where a condition is shown when the project lacks the system.

## 3. What you must decide

Where each of the three is shown.

## 4. What you need to know to decide

The business that runs Taktus itself (DEC-0201) holds real systems: payments, costs, a coding
practice. Its instance sends product findings to the project (UC-6.12), so a run there can be
evidence without its data reaching the project. Every connector already passes its conformance
suite against a fake.

## 5. Options

### Option A — shown where the system is, the project keeps the fakes (recommended)

- **Meaning:**
  1. The first beta condition is met when a stage-1 process of UC-03 runs against the real
     service on the instance of the business, and the business confirms it. The project's own
     instance shows the same process against the fakes.
  2. The removal condition counts an alternative for a capability the project does not use as
     present when the alternative passes its conformance suite against its stand-in.
  3. #210 is proven with the accelerator at a tenant that has one. The project proves the bench
     on an ordinary processor, and NEED-0023 is closed.
- **Consequence:** no account and no hardware are needed from you. The beta waits for the
  business's run instead of the project's.
- **Effort:** the roadmap's three lines and the status rewritten.
- **Reversibility:** cheap; a later account brings the run back to the project's instance.
- **Why recommended:** it follows DEC-0225 and DEC-0201. The evidence comes from where the system
  really is.

### Option B — the roadmap as written

- **Meaning:** you provide what the project lacks: a team organisation at Anthropic (it needs a
  business), an account at a second coding agent's vendor, and an accelerator.
- **Consequence:** the conditions are shown on the project's own instance.
- **Reversibility:** the accounts cost money every month.

### Option C — your own wording, item by item

## 6. What is blocked

Nothing now. The beta waits for the first condition either way.

## 7. How to answer

"DEC-0226: Option A.", "DEC-0226: Option B." or your own wording, item by item, in the issue.
