# NTC-0209 — The coding agent's starting context and its growth were measured

**Mode entry:** M2.8
**Kind:** spend
**Decided:** 2026-10-14
**Raised in:** the pull request that adds `docs/research/2026-10-14-the-coding-worker-and-what-taktus-keeps.md`

## 1. What was decided

The research for the owner's question of 2026-10-14 — what the coding worker should do and what
Taktus keeps — spent on the coding agent to measure two facts that could not be derived from the
ledger:

1. **The agent's fixed starting context:** 14 688 tokens in an empty folder and 22 094 in this
   repository, so the repository's instructions and state add about 7 400 tokens.
2. **How fast its context grows:** about 1 300 tokens per turn over 15 turns of P-03's real
   assignment for #256.

## 2. The evidence

Three local runs of the coding agent with the model of DEC-0019, on 2026-10-14. The figures are
in the research document, §2.3. The cost: USD 0.20 at list price.

## 3. What was considered

- **Deriving the starting context from the instance's ledger.** The ledger sums plain input,
  cache writes and cache reads into one figure, so it cannot be split. Not possible.
- **Measuring on the instance.** A run there is a P-03 run with outward effects. Not taken.

## 4. Which entry permits it

M2.8 of `docs/decisions/anchors.taktus.md`: spending on a credential the owner provided, to
derive or verify a fact instead of asking, up to USD 1 per task. The spend was USD 0.20, on the
local login of the coding agent, for the research the owner asked for.
