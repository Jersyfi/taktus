"""The removal test of the connectors over open standards (S-01, ADR-0111, issue #441), and of
the connectors for the systems a business names (ADR-0150, issue #447).

Each connector is configured beside the loopback, as `TAKTUS_CONNECTORS` would configure it,
and the removal test is run for it, exactly as for every other integration. No registered
process uses any of them yet, so each is `untested`: nothing was exercised, and its maturity
says what is missing. The verdict names the configuration it was taken under — the
connector's capabilities and operations as it declares them — which is how the removal test of
`0.5.0`, once a process of the second tenant uses one, will be told apart from this one.
"""

from __future__ import annotations

from typing import Any

import pytest

from integration.test_removal_test import RECORDS, connector_services, result_of, run_removal
from taktus.adapters.driven.connectors.aws.operations import Config as BillingConfig
from taktus.adapters.driven.connectors.aws.server import build_server as billing_server
from taktus.adapters.driven.connectors.httpcheck.operations import Config as CheckConfig
from taktus.adapters.driven.connectors.httpcheck.server import build_server as check_server
from taktus.adapters.driven.connectors.mail.protocol import Config as MailConfig
from taktus.adapters.driven.connectors.mail.server import build_server as mail_server
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.openai.operations import Config as ModelCostsConfig
from taktus.adapters.driven.connectors.openai.server import build_server as model_costs_server
from taktus.adapters.driven.connectors.prometheus.operations import Config as MetricsConfig
from taktus.adapters.driven.connectors.prometheus.server import build_server as metrics_server
from taktus.adapters.driven.connectors.sentry.operations import Config as ErrorsConfig
from taktus.adapters.driven.connectors.sentry.server import build_server as errors_server
from taktus.adapters.driven.connectors.stripe.operations import Config as PaymentsConfig
from taktus.adapters.driven.connectors.stripe.server import build_server as payments_server
from taktus.components.run.domain.model import RunState

# Nothing is reached: the removal test reads each declaration and calls no operation.
SERVERS: dict[str, Any] = {
    "mail": lambda: mail_server(
        MailConfig(
            imap_host="127.0.0.1",
            smtp_host="127.0.0.1",
            user="support@mail.example",
            address="support@mail.example",
            security="none",
        )
    ),
    "metrics": lambda: metrics_server(MetricsConfig("http://127.0.0.1:9")),
    "check": lambda: check_server(CheckConfig("http://127.0.0.1:9")),
    "billing": lambda: billing_server(BillingConfig("http://127.0.0.1:9")),
    "model-costs": lambda: model_costs_server(ModelCostsConfig("http://127.0.0.1:9")),
    "errors": lambda: errors_server(ErrorsConfig("http://127.0.0.1:9", organization="example")),
    "payments": lambda: payments_server(PaymentsConfig("http://127.0.0.1:9")),
}
SERVES = {
    "mail": ["channel.mail", "mail.messages"],
    "metrics": ["metrics.series"],
    "check": ["check.http"],
    "billing": ["billing.costs"],
    "model-costs": ["models.costs"],
    "errors": ["errors.issues"],
    "payments": ["payments.subscriptions"],
}


@pytest.mark.parametrize("name", sorted(SERVERS))
async def test_a_connector_no_process_uses_is_untested_and_names_what_it_serves(
    name: str,
) -> None:
    services = connector_services(McpActionConnector(SERVERS[name](), timeout=10.0))  # type: ignore[arg-type]
    run = await run_removal(services, RECORDS)
    assert run.state is RunState.FINISHED, run.reason
    result = (await result_of(services, run, "exercise"))["output"]
    assert result["verdict"] == "untested"
    assert result["reason"] == "no registered process uses this integration"
    assert result["configuration"]["adapter"] == RECORDS
    assert sorted(result["configuration"]["serves"]) == SERVES[name]
    assert result["configuration"]["version"] == "1.0.0"
    recorded = (await result_of(services, run, "record"))["output"]
    assert recorded["maturity"] == "experimental"
    assert any("no registered process" in gap for gap in recorded["missing"])
