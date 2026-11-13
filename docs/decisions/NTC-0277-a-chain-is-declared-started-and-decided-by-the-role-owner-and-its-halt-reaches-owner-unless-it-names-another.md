# NTC-0277 — A chain is declared, started and decided by the role `owner`, and its halt reaches `owner` unless it names another

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** branch `area/chains` (final round before 1.0, concept mode, DEC-0236)
**How it follows:** UC-15.4 requires that a chain is a declared object, and that a halted
handover escalates to a person (UC-4.5). No source names who may declare or start a chain, nor
to whom its escalation goes when the chain names nobody. The precedent is the value stream:
only the role `owner` declares one (ADR-0159 §6), because a stream spans processes with owners
of their own. A chain spans processes in the same way. For the escalation, ADR-0252 already
sends a process's escalation to `owner` where the version names no role. The same default holds
for a chain. Strict in substance, sparing in ceremony: every halt is delivered, and the role only
says to whom.

## 1. What was decided

- `PUT /chains/{chain}`, `POST /chains/{chain}/runs` and `POST /chain-runs/{id}/decision` need
  the role `owner` (ADR-0301 §4).
- A chain without `escalation` sends its halted handover's package to the role `owner`, by the
  path `channel` (ADR-0302 §2). A chain may name another role. A role, never a person
  (principle 14).

## 2. The evidence

- `tests/adapters/rest/test_chains.py`: a person without the role `owner` cannot declare, start
  or decide a chain; one with it can.
- `tests/composition/test_chains.py::test_a_halted_handover_reaches_a_person_with_its_situation_package`:
  without `escalation`, the report reaches `owner`.

## 3. What was considered

- **Anyone who may see every linked process.** Rejected: seeing a process is not the right to
  run it in another order with another's inputs. Steering a process is a right of a role
  (ADR-0293); a chain's own right per role can follow when a tenant asks for it.
- **The owner of the receiving process.** Rejected: a process names no owner role the chain
  could read, and the halt is about the chain, not the link.

## 4. Which entry permits it

M2.6, with ADR-0159 §6, ADR-0252 and NTC-0269's M2.14 as precedent. The owner may overrule
it in the pull request.

## 5. The entry it proposes

None beyond NTC-0269's M2.14, a right a use case names without naming the role that holds it
is held by the role `owner`, and the existing default of ADR-0252 for the role an escalation
reaches.
