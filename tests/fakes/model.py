"""A model behind the port that answers what its script says, in memory."""

from __future__ import annotations

from dataclasses import dataclass, field

from taktus.ports.model import Calculability, Completion, Model, ModelAtLimit, ModelError, Prompt
from taktus.shared.v1 import PriceKinds


@dataclass
class FakeModel(Model):
    answer: str = "## Acceptance criteria\n\n- [ ] it works\n"
    name: str = "fake-model@1"
    finish: str = "stop"
    unreachable: str | None = None
    at_limit: int = 0
    """Answer the next so many calls at the provider's rate limit, as a 429 does."""
    prompts: list[Prompt] = field(default_factory=list)
    declaration: Calculability = field(
        default_factory=lambda: Calculability(
            input_count="exact",
            output_cap="hard",
            usage_kinds=("input", "output"),
            billing="per_token",
        )
    )
    """What the fake says it can compute; a test sets `input_count="none"` to see the step
    refused for want of an estimate, or `billing="per_window"` to see the budget say so."""

    def calculability(self) -> Calculability:
        return self.declaration

    async def count(self, prompt: Prompt) -> int | None:
        if self.declaration.input_count == "none":
            return None
        return _words(prompt)

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        if self.unreachable is not None:
            raise ModelError(self.unreachable)
        if self.at_limit > 0:
            self.at_limit -= 1
            raise ModelAtLimit("the provider's rate limit is reached")
        tokens_in = _words(prompt)
        tokens_out = len(self.answer.split())
        return Completion(
            text=self.answer,
            model=self.name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            by_kind=PriceKinds(input=tokens_in, output=tokens_out),
            finish=self.finish,  # type: ignore[arg-type]
        )


def _words(prompt: Prompt) -> int:
    """Tokens counted as words: the fake's tokenizer, the same before and after the call."""
    return len(prompt.user.split()) + len((prompt.system or "").split())
