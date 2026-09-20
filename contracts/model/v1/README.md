# Model contract v1

*The schema and the conformance suite are not yet written.* What exists is the core's side of
the contract: the model port (`src/taktus/ports/model.py`) — a prompt in, a completion out with
the tokens used, the model that answered and why it stopped — and its adapter over the
chat-completions dialect most endpoints answer (`src/taktus/adapters/driven/models/`). When this
contract is written as JSON Schema, the port is held to it by `tests/contract` the way the
worker and connector ports are held to theirs. `docs/architecture/contracts.md` §2.3 states what
the contract requires.
