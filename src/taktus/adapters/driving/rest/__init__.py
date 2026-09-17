"""The HTTP driving adapter: health, readiness, webhook intake, and a read API — every path
under a configurable prefix, every error an RFC 9457 problem."""

from taktus.adapters.driving.rest.app import build_app
from taktus.adapters.driving.rest.wiring import RestServices

__all__ = ["RestServices", "build_app"]
