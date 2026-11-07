"""Where the connectors to Google's APIs exchange a service account key: the endpoint configured,
else Google's while the API is Google's own, else `<target>/token` — never the key's own
`token_uri`, which a key could point anywhere."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import pytest
from taktus_connectors.appstores.config import PLAY
from taktus_connectors.appstores.config import Config as Stores
from taktus_connectors.bigquery.operations import TARGET as WAREHOUSE
from taktus_connectors.bigquery.operations import Config as Warehouse
from taktus_connectors.cloudfunctions.operations import TARGET as FUNCTIONS
from taktus_connectors.cloudfunctions.operations import Config as Functions
from taktus_connectors.cloudrun.operations import TARGET as SERVERLESS
from taktus_connectors.cloudrun.operations import Config as Serverless
from taktus_connectors.firebase.operations import TARGET as SITES
from taktus_connectors.firebase.operations import Config as Sites
from taktus_connectors.googleanalytics.operations import TARGET as ANALYTICS
from taktus_connectors.googleanalytics.operations import Config as Analytics

GOOGLE = "https://oauth2.googleapis.com/token"
CONFIGURED = "https://tokens.example/token"
FAKE = "http://host.docker.internal:9999"


class Exchanging(Protocol):
    def token(self) -> str: ...


type Make = Callable[[str | None, str], Exchanging]
"""A connector's configuration at an address (its default where None), with an endpoint."""

MAKERS: dict[str, Make] = {
    "functions": lambda t, e: Functions(t or FUNCTIONS, "p", "l", token_endpoint=e),
    "warehouse": lambda t, e: Warehouse(t or WAREHOUSE, token_endpoint=e),
    "serverless": lambda t, e: Serverless(t or SERVERLESS, "p", "l", token_endpoint=e),
    "sites": lambda t, e: Sites(t or SITES, token_endpoint=e),
    "analytics": lambda t, e: Analytics(t or ANALYTICS, token_endpoint=e),
    "stores": lambda t, e: Stores(t or PLAY, t or PLAY, token_endpoint=e),
}


@pytest.mark.parametrize("name", sorted(MAKERS))
def test_google_s_own_api_exchanges_at_google_s_token_endpoint(name: str) -> None:
    assert MAKERS[name](None, "").token() == GOOGLE


@pytest.mark.parametrize("name", sorted(MAKERS))
def test_another_address_serves_the_token_endpoint_beside_its_api(name: str) -> None:
    assert MAKERS[name](FAKE, "").token() == f"{FAKE}/token"


@pytest.mark.parametrize("name", sorted(MAKERS))
def test_a_configured_endpoint_wins(name: str) -> None:
    assert MAKERS[name](FAKE, CONFIGURED).token() == CONFIGURED
    assert MAKERS[name](None, CONFIGURED).token() == CONFIGURED
