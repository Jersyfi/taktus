"""The operations the cloud operations connector serves, by name.

`api` holds the configuration, the access token and one request; `logs`, `billing`,
`secrets`, `metrics` and `models` each ask and read one API.
"""

from __future__ import annotations

from taktus_connectors.gcp import billing, logs, metrics, models, secrets
from taktus_connectors.gcp.api import Config

__all__ = ["OPERATIONS", "Config"]

OPERATIONS = {
    "logs.query.entries": logs.entries,
    "billing.costs.daily": billing.daily,
    "secrets.metadata.list": secrets.list_,
    "metrics.series.query": metrics.query,
    "metrics.series.range": metrics.range_,
    "models.costs.daily": models.costs,
    "models.catalogue.list": models.catalogue,
}
