"""The read side of the decision component (CQRS)."""

from taktus.components.decision.application.query.requests import Addressed, DecisionQueries

__all__ = ["Addressed", "DecisionQueries"]
