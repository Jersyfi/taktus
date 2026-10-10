"""The read side of the reporting component (CQRS)."""

from taktus.components.reporting.application.query.levels import LevelQueries
from taktus.components.reporting.application.query.reports import ReportQueries, view

__all__ = ["LevelQueries", "ReportQueries", "view"]
