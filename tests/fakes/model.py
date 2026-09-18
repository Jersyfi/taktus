"""A model behind the port that answers what its script says, in memory."""

from __future__ import annotations

from dataclasses import dataclass, field

from taktus.ports.model import Completion, Model, ModelError, Prompt


@dataclass
class FakeModel(Model):
    answer: str = "## Acceptance criteria\n\n- [ ] it works\n"
    name: str = "fake-model@1"
    finish: str = "stop"
    unreachable: str | None = None
    prompts: list[Prompt] = field(default_factory=list)

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        if self.unreachable is not None:
            raise ModelError(self.unreachable)
        return Completion(
            text=self.answer,
            model=self.name,
            tokens_in=len(prompt.user.split()) + len((prompt.system or "").split()),
            tokens_out=len(self.answer.split()),
            finish=self.finish,  # type: ignore[arg-type]
        )
