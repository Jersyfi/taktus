# Warp and Taktus, 2026-10-13

The owner found Warp (warp.dev) close to Taktus. The owner asked two questions: whether Warp
solves parts of what Taktus wants better, and whether Taktus must change at its foundations. The
session could question any foundation that Warp provably and lastingly solves better. The owner
accepted the outcome in DEC-0195.

**Sources, all read on 2026-10-13:**

- Warp's complete documentation, taken from its export at `docs.warp.dev/llms.txt`;
- its OpenAPI specification;
- its pricing and enterprise pages;
- press coverage.

The load-bearing statements were checked in Warp's own documentation. Each is marked below:
*shipped*, *early access* (EA), or *claim* when no independent source confirms it.

## 1. What Warp is

Warp began as a terminal. Since 2026-08-18 its home page leads with "Open Infrastructure for
Cloud Software Factories". It sells three products: Factories, the terminal and an agent command
line.

- **Factories** (EA since 2026-08). A factory turns issues, tickets and chat messages into
  reviewed pull requests.
  - Role agents do the work: Foreman, Triage, Spec, Implement, Review. The Foreman is a language
    model, and it decides the next step.
  - A factory is defined as code, in `factory.yaml`. The definition lists agents, automations,
    runners, routers, scorers, skills and webhooks.
  - A validator runs locally without a login, and a pull-request check validates changes.
  - Scorers are language-model judges. Benchmarks compare configurations on fixed tasks. After
    25 failures or 7 days, the factory proposes changes to itself as a pull request.
- **Cloud agents** (shipped since 2026-02). Agents start from a schedule, a Slack or Linear event,
  the API or the command line.
  - Each run gets a shareable link.
  - A person can steer a running agent, take its work to their own machine and hand it back.
  - Claude Code, Codex and Gemini can run as interchangeable "harnesses".
- **Self-hosting** (Enterprise only). A worker daemon connects outbound only and runs jobs on
  Docker, Kubernetes or directly on the host. The control plane stays with Warp, and prompts,
  transcripts and orchestration pass through it.
- **Data.** "Data is stored in Google Cloud in the US" (`/enterprise`). Bring-your-own-key is
  allowed only for organisations of up to ten employees. Every cloud run is charged per agent
  hour on top. There is no uptime SLA.
- **Governance as documented by Warp:**
  - spec approval is an instruction in the Foreman's prompt;
  - the review agent's verdict is advisory;
  - picking up a task "doesn't claim, lock, or pause it";
  - orchestration is one level deep;
  - an analytics API returns per-user rollups, offered for productivity dashboards (EA).
- **Trajectory** (claims): about USD 75 M raised, 800 000 developers, and named customers.
  - The client has been open source (AGPL) since 2026-04.
  - Four terminal CVEs were published on 2026-06-24, the highest scored 8.8.

Warp positions itself in software engineering and operations. It makes no claim beyond them.

## 2. Comparison

**Where Warp is ahead of Taktus:**

- the time to a first result;
- steering, handing over and taking back running work;
- execution inside the customer's network, through an outbound-only worker;
- live sight inside a step;
- comparing versions on fixed cases;
- other agents as a channel, through Factory MCP;
- open formats: `SKILL.md`, `.agents/.mcp.json`, rules across harnesses.

**Where the two are even:** several coding agents behind one interface, and a definition kept
as code.

**Where Taktus is ahead:**

- human approval held at a step boundary by an anchor, not by a prompt;
- the method chosen per step, maturing from a language model towards a rule;
- exactness classes;
- a content-free, chained ledger, with provenance per step;
- sovereignty and self-hosting of the whole control plane;
- principle 14, where Warp offers per-user analytics;
- a takeover that holds a lease;
- a budget reserved before each step;
- reach beyond software.

## 3. The core finding

Read against the roadmap's completion criteria, every milestone up to `1.0.0` proved Taktus on
software or IT operations:

- the second tenant was a second software project;
- level 4 was "a release happens end to end";
- the second domain was IT operations.

That is the field where Warp is far ahead. What sets Taktus apart is not proven on a real
operation before `1.0.0`: exact steps, legal anchors, maturation to ML, and departments beyond
IT.

## 4. Foundations examined

1. **Should Taktus become a software factory itself?** No. That layer is commodity, as the
   non-goal "no coding agent and no agent runtime as a core product" says. Taktus uses it as a
   worker.
2. **Should Taktus build on Warp's platform?** No. Warp's control plane is closed and stores in
   the US. That breaks principles 11 and 13 and ADR-0013 C.
3. **Should a language model steer the flow, as Warp's Foreman does?** No. Warp's approvals are
   prompt instructions for exactly that reason. In Taktus the graph decides and a model proposes.
4. **Should the ledger hold transcripts?** No. A transcript becomes an artifact with a retention
   period instead (W8).
5. **Is software the right place for Taktus to prove itself?** No. This is the one foundation
   that changes (W1).

## 5. The proposals and where they land

| | Proposal | Milestone |
|---|---|---|
| W1 | Taktus proves itself on business domains: the second tenant is a real operation; the second domain is "incoming invoice to payment release"; IT operations move after `1.0.0` | `0.4.0`, `0.6.0`, `0.7.0` |
| W2 | the worker contract gains an outbound-only binding, steering and handover before it freezes | `0.6.0` |
| W3 | a person takes over a running step under a lease and hands the result back | `0.5.0` |
| W4 | a first process in ten minutes, measured | `0.5.0` |
| W5 | Taktus as an MCP server, with rights per role | `0.5.0` |
| W6 | `SKILL.md`, `AGENTS.md`, and a bundle validator that needs no instance | `0.4.0` |
| W7 | fixed evaluation cases per process, and versions compared on them | `0.5.0` |
| W8 | the trace inside a step, live and shareable by role | `0.5.0` |
| W9 | vendors' MCP servers as connector candidates, with a manifest of their effects | `0.6.0` |
| W10 | a whole software factory as a worker | `0.6.0` |

**Not adopted:**

- a terminal or a development environment as Taktus's surface (principle 1);
- per-user analytics (principle 14);
- seats plus agent hours as pricing (ADR-0010);
- a language model as the only judge of quality (principle 8);
- hidden model routers (UC-8.2);
- a control plane only the vendor can host (principle 11);
- approvals as prompt instructions (ADR-0008).
