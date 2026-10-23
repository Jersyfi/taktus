# NTC-0221 — A proposed version is rehearsed from the plan dialogue

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-23
**Raised in:** the pull request for [#329](https://github.com/Jersyfi/taktus/issues/329), whose implementation follows in a pull request of its own
**How it follows:** the owner accepted on 2026-10-12 the product outlook, including idea F9, *rehearse a version straight from the plan dialogue* (DEC-0190), and the issue #329 says the use case that requires it is written first. UC-1.10 states exactly that act as four conditions and adds nothing the idea does not ask for. The idea named the live run (UC-6.10) and the exactness statement (UC-6.9) as things to show; UC-1.10 asks for neither beyond what the run level already carries, and leaves the anchors shown as "would halt here" out.

## 1. What was decided

A use case UC-1.10, *A proposed version is rehearsed from the plan dialogue*, is written in state
`specified`, in the component `command`, for version `0.4.0`. Its tests are named in the next
pull request that implements it, because `make gate-usecases` refuses a pull request that changes what a use case
requires and also touches the files of the tests it names.

## 2. The evidence

DEC-0190 lists idea F9 as accepted for `0.4.0` under #329. UC-4.15 already requires a
rehearsal before commissioning but not that the person is offered it from the plan, nor that the
page shows the result. Both are in the idea.

## 3. What was considered

- **Amending UC-4.15.** Rejected: UC-4.15 is the change flow and stays as ADR-0091 says; the
  issue's boundary is *not changing ADR-0091's proposal flow*.
- **Naming the tests now.** Rejected: the gate refuses it in the same pull request.

## 4. Which entry permits it

M2.7, bringing a use case up to what the owner already accepted: a feature the owner accepted in
DEC-0190. The owner may veto it within seven days of the pull request that carries it; a veto
turns it into a request under M3.15.
