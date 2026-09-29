# History

Material from the original project definition that is settled, superseded or no longer
maintained. The definition was written in German, outside this repository, and exists in
several versions; the owner holds them. Where a use case number from it is still quoted, the
mapping to the numbers this repository uses is `docs/usecases/NUMBERING.md`. Kept so that the reasoning is not lost, clearly marked so that nobody mistakes it
for current.

---

## Naming — settled

Candidates considered and rejected: **Dirigo** (several active US software companies, and a US
state motto — the wrong geographic anchor for a European product); **Taktwerk** (an active Swiss
company in process optimisation — direct collision); **Maestro, Cortex, Conductor** (heavily
overused in this field, weak as marks); **OrchestrAI** and similar (descriptive, generic).

Also on the shortlist: **Dirigon** (from *dirigere*, to direct — the solid runner-up),
**Cadenzo** (from *cadenza*, the moment of free virtuosity within the work — the most elegant
story), **Batuta** (the conductor's baton in Spanish, Romanian and Polish — very European, needs
explaining), **Orchestrio** (immediately understandable, least distinctive).

**Chosen: Taktus.** The *tactus* was the hand motion that held a Renaissance ensemble together,
the ancestor of conducting. German *Takt* plus a Latin ending. European cultural history, short,
pronounceable across EU languages.

`taktus.eu` is held by the owner. Trademark and register checks remain the owner's to complete
before any commercial launch.

## Architecture guardrails — superseded by the ADRs

The original chapter 5 described three layers, the adapter obligation, the removal test,
capabilities instead of product names, telemetry from day one, and the integration code in two
tiers. All of it is now decided and enforced in `docs/adr/` and `docs/architecture/`, in more
detail and with the boundaries of each promise stated.

Where the chapter and an ADR disagree, **the ADR wins**. The chapter is not maintained.

## Development path — superseded by the roadmap

The original chapter 9 described five phases. `docs/roadmap.md` is the maintained version and
carries the real completion criteria.

The one idea from it that still governs and now lives in the roadmap: **nothing from a later
phase is built while the architecture tests and the removal test of the previous one are not
automated.**

## Open questions — resolved or moved

The original chapter 11 listed nine questions for the owner. Their current state:

| Question | Where it stands |
|---|---|
| A fifteenth principle for "own core, interchangeable execution" | Not added. It is contained in principle 13 |
| Placement of the architecture chapter | Moot — dissolved into the ADRs |
| "Taktus catalogue" as an umbrella term | Kept |
| Whether to make an idea from the outlook binding in v1 | No. A bundle is a set of plain files a person writes and registers (ADR-0011), so what defines a process already lives outside Taktus; exporting a registered version back out does not exist yet. The open specification stays after 1.0.0 |
| The maturity threshold for autonomy level 3 | Kept at *verified* from level 3 |
| Product names in the market chapter | Removed. `market.md` names categories, not products |
| A lower bound for automatic skill approval | **Still open**: DEC-0028. Belongs with the skill lifecycle |
| The second reference domain | Finance, as originally proposed. Unchanged |
| Who reviews the legal-anchor catalogue, and when | **Still open**: DEC-0029. Needed before any finance or personnel blueprint goes live |

The two still open are carried as decision requests, DEC-0028 and DEC-0029, not as a chapter.
