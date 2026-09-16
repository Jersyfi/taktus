"""The worker port over HTTP and Server-Sent Events, as contracts/worker/v1 defines them."""

from taktus.adapters.driven.workers.http.client import HttpWorker

__all__ = ["HttpWorker"]
