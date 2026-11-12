"""Models: behind the model port. `openai_compatible/` speaks the chat-completions dialect most
endpoints answer — a vendor's API, a local server — and `vertex/` the generateContent interface
of a cloud's regional endpoint; they are the only places a product's wire format lives
(README.md). `pool.py` maps purposes to configured models."""

from taktus.adapters.driven.models.openai_compatible import OpenAiCompatibleModel
from taktus.adapters.driven.models.pool import Declared, StaticModelPool

__all__ = ["Declared", "OpenAiCompatibleModel", "StaticModelPool"]
