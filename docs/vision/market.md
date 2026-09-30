# Market picture

> **Stale by construction. Last established: September 2026. Not currently maintained.**
>
> The definition (version 2) dates its market chapter September 2026. Its two figures are
> attributed to an analyst firm by name, with no report, date or link, and neither has been
> checked since. Its categories named product examples, which this file leaves out. This file
> also differs from that chapter: it adds process mining and the gap "the right kind of AI per
> step", both from later conversation and without research, and it leaves out the category of
> development-only orchestration and the gap "own core, interchangeable execution", which is
> principle 13 now. Do not use any of it in anything published, in a pitch or in a decision. The first pull request that needs a
> market statement re-establishes it with sources and access dates and replaces this file.
>
> It is kept because the *shape* of the analysis — the categories and where the gap is — has
> held up, and because deleting it would lose the reasoning behind the positioning.

## The categories, and what each lacks

| Category | Strength | What is missing for this vision |
|---|---|---|
| Workflow automation with AI nodes | visual building, large connector libraries | AI is an add-on, not the core; manual building and testing remain |
| RPA plus agentic AI | enterprise governance, protection of existing RPA | heavy, expensive, aimed at large RPA estates, nothing for individuals |
| Code-first agent frameworks | maximum control for developers | a construction kit, not a product; no reporting or controlling layer |
| Enterprise suites with agent builders | deep integration into one ecosystem | lock-in to cloud, models and tools; no real sovereignty |
| Personal agent runtimes and CLI orchestrators | channels, memory, fast model switching | single-user; no governance levels, no views, no tenancy; high churn |
| LLM observability and eval platforms | tracing, evaluations, prompt versioning, per-call cost | not an orchestrator; no process model, no governance |
| Process mining | finds the processes that exist | describes; does not run |

The last three are not competitors. A personal agent runtime is a **worker candidate**; an
observability platform is an **optional backend**.

## The gap

No product combines all of these:

1. AI as the core, rather than AI nodes on a workflow engine
2. **The right kind of AI per step** — rule, statistics, classical ML, specialised neural
   models, language models — chosen, justified and matured over time
3. Fully model- and tool-agnostic, including local models on the operator's own hardware
4. Coupled and decoupled process control, freely mixable
5. Role-based transparency from employee to investor, with bus-factor protection as a design
   principle
6. The entire autonomy range, at every size
7. European sovereignty: self-hosting for anyone, data protection as a feature
8. Real vendor freedom, proven by a removal test rather than asserted
9. Enablement as part of the product, not a prerequisite

Point 2 is the newest and, on current evidence, the most defensible: the field treats AI as a
synonym for language models, and a product that does not is hard to imitate without rebuilding
its core.

## Two claims that were carried for a long time without a citation

Both appeared in the definition's market chapter, the first attributed to Gartner, the second
unattributed, neither with a report, a date or a link. Neither has been verified:

- that around 40 % of enterprise applications would embed task-specific agents by the end of
  2026
- that more than 40 % of agentic AI projects are at risk of cancellation by 2027

Treat both as uncited until re-established. The second matters most, because the stated
reasons — missing governance, observability and unclear return — are the three things this
product is built around. If it is not true, the positioning rests on less than it appears to.
