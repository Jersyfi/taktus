# NTC-0092 — The suites' meta-tests run as the instance runs them

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** the pull request of issue #93

## 1. What was decided

The meta-tests of the worker and the connector suite — one run per fault the reference adapter
can inject, which must fail exactly that check — now run the suite the way the instance runs it.
The instance's configuration names the endpoint, the task, the scenario, the credential and the
adapter's log. The catalog's one writer records the run. Each test asserts what it asserted before,
on the report the record's evidence holds. It also asserts that the run is recorded as not
passed, with exactly that check.

A new file, `tests/conformance/test_recorded.py`, records a passing reference worker, a passing
reference connector and a passing model adapter, and the model endpoint's faults. A new
integration test, `tests/integration/test_conformance_maturity.py`, goes through the run engine:
*verified* after a pass and a `changed` removal verdict, *experimental* once the configuration
changes. The tests that run the suite as a third party would — `conformance run`, the reference
tests, the coding worker's, the chat connector's — are unchanged.

## 2. The evidence

- Issue #93, *How it is verified*: "Each fault the reference adapter can inject is recorded as not
  passed, naming that check."
- Running each fault twice — once as a third party, once through the instance — would double the
  meta-tests' cost. Measured on the session's machine: the worker and connector fault tests take
  70 seconds together through the instance; a second set beside them would add about as much
  again. `make gate-conformance` as a whole took 255 seconds there with this change.
- The report the instance records is the suite's own report (`Report.to_dict`), so every assertion
  the meta-tests made on the report object holds on the recorded document.

## 3. What was considered

- **A second, parallel set of fault tests through the instance.** Rejected: the same faults twice,
  for no assertion the single set cannot make.
- **Recording only one fault per family.** Rejected: the issue asks for each fault.

## 4. Which entry permits it

M2.2, "A change of test strategy and what the tests now cover". The change moves where the
meta-tests enter the suite and adds what they assert; it weakens no gate (M2.3) and changes no
requirement (M3.15). `tests/README.md` and `tests/conformance/README.md` say the same.
