"""The operations the cloud operations connector serves, by name.

`api` holds the configuration, the access token and one request; `logs`, `billing` and
`secrets` each ask and read one API.
"""

from __future__ import annotations

from taktus_connectors.gcp import billing, logs, secrets
from taktus_connectors.gcp.api import Config

__all__ = ["OPERATIONS", "Config"]

OPERATIONS = {
    "logs.query.entries": logs.entries,
    "billing.costs.daily": billing.daily,
    "secrets.metadata.list": secrets.list_,
}
