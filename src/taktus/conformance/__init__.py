"""The conformance suite: the executable reading of a contract, run against a live adapter.

`docs/architecture/contracts.md` §3 calls the suite the real asset — not the adapter code, but the
ability to check. This package is that ability for the worker contract and for the connector
contract. It imports nothing from the rest of Taktus: no component, no port, no adapter. It talks
to a worker over HTTP and SSE, and to a connector over MCP, exactly as a foreign control plane
would, so that an adapter written in any language can be checked by anyone who can install this
package.

Entry points: `taktusctl conformance run` (src/taktus/adapters/driving/cli) and the gate under
tests/conformance. What both contracts share — the report, the findings, the catalogue of checks,
the schema validators — lives at this level; what is the worker's is `rules`, `client` and
`suite`; what is the connector's is under `connector/`.
"""

from taktus.conformance.connector.suite import ConnectorSuiteOptions, run_connector_suite
from taktus.conformance.report import CheckResult, Report, Status
from taktus.conformance.suite import SuiteOptions, run_suite

__all__ = [
    "CheckResult",
    "ConnectorSuiteOptions",
    "Report",
    "Status",
    "SuiteOptions",
    "run_connector_suite",
    "run_suite",
]
