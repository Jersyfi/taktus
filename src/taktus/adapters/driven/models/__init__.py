"""Models: behind the model port. `openai_compatible/` speaks the chat-completions dialect most
endpoints answer — a vendor's API, a local server — and is the only place a product's wire
format lives; `pool.py` maps purposes to configured models."""

from taktus.adapters.driven.models.openai_compatible import OpenAiCompatibleModel
from taktus.adapters.driven.models.pool import StaticModelPool

__all__ = ["OpenAiCompatibleModel", "StaticModelPool"]
