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
from taktus_connectors.anthropic.operations import Config as CostReportConfig
from taktus_connectors.anthropic.server import build_server as cost_report_server
from taktus_connectors.appstore.operations import Config as StoreConfig
from taktus_connectors.appstore.server import build_server as store_server
from taktus_connectors.appstores.operations import Config as StoresConfig
from taktus_connectors.appstores.server import build_server as stores_server
from taktus_connectors.aws.operations import Config as BillingConfig
from taktus_connectors.aws.server import build_server as billing_server
from taktus_connectors.bigquery.operations import Config as WarehouseConfig
from taktus_connectors.bigquery.server import build_server as warehouse_server
from taktus_connectors.cloudrun.operations import Config as ServerlessConfig
from taktus_connectors.cloudrun.server import build_server as serverless_server
from taktus_connectors.firebase.operations import Config as SiteReleasesConfig
from taktus_connectors.firebase.server import build_server as site_releases_server
from taktus_connectors.gcp.api import Config as CloudConfig
from taktus_connectors.gcp.server import build_server as cloud_server
from taktus_connectors.googleanalytics.operations import Config as AnalyticsConfig
from taktus_connectors.googleanalytics.server import build_server as analytics_server
from taktus_connectors.httpcheck.operations import Config as CheckConfig
from taktus_connectors.httpcheck.server import build_server as check_server
from taktus_connectors.kubernetes.operations import Config as WorkloadsConfig
from taktus_connectors.kubernetes.server import build_server as workloads_server
from taktus_connectors.loki.operations import Config as LogsConfig
from taktus_connectors.loki.server import build_server as logs_server
from taktus_connectors.mail.protocol import Config as MailConfig
from taktus_connectors.mail.server import build_server as mail_server
from taktus_connectors.mailchimp.operations import Config as NewsletterConfig
from taktus_connectors.mailchimp.server import build_server as newsletter_server
from taktus_connectors.netlify.operations import Config as SiteDeploysConfig
from taktus_connectors.netlify.server import build_server as site_deploys_server
from taktus_connectors.openai.operations import Config as ModelCostsConfig
from taktus_connectors.openai.server import build_server as model_costs_server
from taktus_connectors.prometheus.operations import Config as MetricsConfig
from taktus_connectors.prometheus.server import build_server as metrics_server
from taktus_connectors.sentry.operations import Config as ErrorsConfig
from taktus_connectors.sentry.server import build_server as errors_server
from taktus_connectors.stripe.operations import Config as PaymentsConfig
from taktus_connectors.stripe.server import build_server as payments_server
from taktus_connectors.vault.operations import Config as SecretsConfig
from taktus_connectors.vault.server import build_server as secrets_server
from taktus_connectors.vercel.operations import Config as SiteDeploymentsConfig
from taktus_connectors.vercel.server import build_server as site_deployments_server
from taktus_connectors.wordpress.operations import Config as WebsiteConfig
from taktus_connectors.wordpress.server import build_server as website_server

from integration.test_removal_test import RECORDS, connector_services, result_of, run_removal
from taktus.adapters.driven.connectors.mcp import McpActionConnector
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
    "cost-report": lambda: cost_report_server(CostReportConfig("http://127.0.0.1:9")),
    "errors": lambda: errors_server(ErrorsConfig("http://127.0.0.1:9", organization="example")),
    "payments": lambda: payments_server(PaymentsConfig("http://127.0.0.1:9")),
    "workloads": lambda: workloads_server(WorkloadsConfig("http://127.0.0.1:9")),
    "cloud": lambda: cloud_server(CloudConfig.at("example", target="http://127.0.0.1:9")),
    "logs": lambda: logs_server(LogsConfig("http://127.0.0.1:9")),
    "secrets": lambda: secrets_server(SecretsConfig("http://127.0.0.1:9")),
    "store": lambda: store_server(StoreConfig("http://127.0.0.1:9")),
    "stores": lambda: stores_server(StoresConfig("http://127.0.0.1:9", "http://127.0.0.1:9")),
    "serverless": lambda: serverless_server(
        ServerlessConfig("http://127.0.0.1:9", "example", "europe-west1")
    ),
    "site-releases": lambda: site_releases_server(SiteReleasesConfig("http://127.0.0.1:9")),
    "site-deploys": lambda: site_deploys_server(SiteDeploysConfig("http://127.0.0.1:9")),
    "site-deployments": lambda: site_deployments_server(
        SiteDeploymentsConfig("http://127.0.0.1:9")
    ),
    "newsletter": lambda: newsletter_server(NewsletterConfig("http://127.0.0.1:9")),
    "website": lambda: website_server(WebsiteConfig("http://127.0.0.1:9")),
    "analytics": lambda: analytics_server(AnalyticsConfig("http://127.0.0.1:9", "123456789")),
    "warehouse": lambda: warehouse_server(
        WarehouseConfig("http://127.0.0.1:9", "example", "product_copy")
    ),
}
SERVES = {
    "mail": ["channel.mail", "mail.messages"],
    "metrics": ["metrics.series"],
    "check": ["check.http"],
    "billing": ["billing.costs", "logs.query", "secrets.metadata"],
    "model-costs": ["models.catalogue", "models.costs"],
    "cost-report": ["models.catalogue", "models.costs"],
    "errors": ["errors.issues"],
    "payments": ["payments.customers", "payments.subscriptions"],
    "workloads": ["deployment.workloads"],
    "cloud": ["billing.costs", "logs.query", "secrets.metadata"],
    "logs": ["logs.query"],
    "secrets": ["secrets.metadata"],
    "store": ["expiry.credentials"],
    "stores": ["stores.beta", "stores.releases"],
    "serverless": ["deployment.workloads"],
    "site-releases": ["deployment.sites"],
    "site-deploys": ["deployment.sites"],
    "site-deployments": ["deployment.sites"],
    "newsletter": ["newsletter.broadcasts"],
    "website": ["website.posts"],
    "analytics": ["analytics.reports"],
    "warehouse": ["warehouse.queries"],
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
