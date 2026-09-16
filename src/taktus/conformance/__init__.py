"""The conformance suite: the executable reading of a contract, run against a live adapter.

`docs/architecture/contracts.md` §3 calls the suite the real asset — not the adapter code, but the
ability to check. This package is that ability for the worker contract. It imports nothing from
the rest of Taktus: no component, no port, no adapter. It talks to a worker over HTTP and SSE
exactly as a foreign control plane would, so that a worker written in any language can be checked
by anyone who can install this package.

Entry points: `taktusctl conformance run` (src/taktus/adapters/driving/cli) and the gate under
tests/conformance. The stream rules in `rules` are pure and also prove the fixtures under
contracts/worker/v1/examples/transcript known good or known bad.
"""

from taktus.conformance.report import CheckResult, Report, Status
from taktus.conformance.suite import SuiteOptions, run_suite

__all__ = ["CheckResult", "Report", "Status", "SuiteOptions", "run_suite"]
