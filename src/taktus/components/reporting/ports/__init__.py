"""Ports this component needs beyond the cross-cutting ones."""

from taktus.components.reporting.ports.decisions import (
    DecisionAnswers,
    DecisionRead,
    DecisionRefused,
)
from taktus.components.reporting.ports.deliveries import Deliveries, NotDelivered, Sent
from taktus.components.reporting.ports.findings import (
    Blocks,
    ChannelIncomplete,
    FindingChannel,
    Held,
)
from taktus.components.reporting.ports.interfaces import Failures
from taktus.components.reporting.ports.phrasebooks import Phrasebooks
from taktus.components.reporting.ports.secret_values import SecretValues

__all__ = [
    "Blocks",
    "ChannelIncomplete",
    "DecisionAnswers",
    "DecisionRead",
    "DecisionRefused",
    "Deliveries",
    "Failures",
    "FindingChannel",
    "Held",
    "NotDelivered",
    "Phrasebooks",
    "SecretValues",
    "Sent",
]
