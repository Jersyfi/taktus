# The coding worker, and what Taktus keeps — 2026-10-14

**Why this file exists.** The owner asked what is proportionate in P-03, the process that turns a
handed issue into a pull request. Its coding step gives a coding agent a long list of
requirements, even for small tasks. The owner's claim: a coding agent can already do many of the
process steps itself, perhaps better, and handles caching on its own. The owner asked for the
market, for research, and for a way forward that keeps the cost in proportion to the benefit.
Two further points of the owner's frame this file. The language a worker uses inside the machine
does not matter to a person. Everything a person reads must have the form the customer chose, and
Taktus should know general principles of what a person understands, so that no customer starts
from zero.

**How it was made.** A session read P-03 version 9, the coding worker and its README, and the
records of the runs. It read the instance's ledger of the last 72 hours through the read-only
monitor job of DEC-0197. It measured the coding agent locally in three calls (section 2.3). Web
sources were read on 2026-10-14; each claim names its source in section 9.

**It expires.** The figures describe P-03 version 9, the coding agent 2.1.295 on the instance
(2.1.292 locally), and prices of 2026-10-14. Each proposal of section 7 becomes an issue that
states its own verification condition.

**Terms used here.**

- A **turn** is one call of the agent to its model. The agent sends its whole conversation each
  time and receives one answer, which usually calls one tool.
- The **context** of a turn is everything sent in it: the agent's own instructions, its tool
  definitions, the repository's instruction file, the task, and every earlier tool call with its
  output.
- **Prompt caching** means the provider keeps the start of a context it has seen. A later call
  that starts with the same text pays a reduced price for that part. Writing text into the cache
  costs more than plain input; reading it costs much less (section 4).
- The **assignment** is what Taktus hands the worker: a goal, acceptance criteria and inputs
  (`contracts/worker/v1`).

---

## 1. The question

What should Taktus cover with its own process steps, and what should the coding worker work out
by itself, so that a merged pull request costs a sensible amount? Where may machine-internal text
be terse or compressed, and where must it be written for a person?

## 2. What was measured

### 2.1 What P-03 asks of the worker

P-03 version 9 has 24 steps in sequence and 3 that run only when a run escalates. One is the
worker's: `implement`. All others are rules, a wait, or connector calls. They cost no model
tokens.

The assignment of `implement` is small. For issue #256 the worker's prompt is **4 541
characters, about 1 100 tokens**:

| Part | Characters |
|---|---|
| The worker's fixed preamble (`worker.py`, `_prompt`) | about 230 |
| The goal | 189 |
| Eight acceptance criteria | 1 950 |
| The inputs: issue number, title, the issue's text and comments | about 2 170 |

The issues handed so far have 800 to 1 700 characters of text and at most one comment.

What makes the assignment expensive is not its size but the work it asks for. Three of the eight
criteria send the agent into the whole repository:

- "the repository's own rules for a change are met: whatever its contribution documentation
  requires". In this repository that is `CLAUDE.md` (21 801 bytes), the anchor pages (34 844
  bytes), `docs/process/` (12 926 bytes) and the pull request template (3 032 bytes). Most of it
  governs sessions: decision records, notices, needs requests, `docs/status.md`.
- "the repository's own checks are run in the workspace and pass". The workspace has none of the
  repository's tools (`make`, `uv`, `pytest`), as the run record of 2026-10-13 states. The agent
  tries, fails, and writes the failure into its summary. The pipeline judges the change anyway.
- "the summary is written in the shape the repository prescribes for a pull request
  description". The agent must find the template and the checks that read it.

Two further criteria describe rules Taktus already enforces itself: the record numbers, which the
run reserves since ADR-0095, and the workflow files, which the service refuses (#366).

### 2.2 What the instance spent, 2026-10-11 to 2026-10-14

From the ledger (`step.finished`, summed per run). `tokens_in` adds plain input, cache writes and
cache reads together (`worker.py`, `_tokens_of`). Money reaches the ledger only for an assignment
that finished; for the others it was estimated at the rate of the five that reported money,
**USD 0.58 per million `tokens_in`**.

| Outcome of the coding step | Runs | `tokens_in` | Money |
|---|---|---|---|
| finished, pull request merged (#373, #387) | 2 | 4.79 M | USD 2.48 reported |
| finished, pull request closed as a duplicate (#415) | 1 | 2.31 M | USD 1.51 reported |
| finished, branch write refused (#256, fixed by #366's change) | 1 | 0.96 M | USD 0.69 reported |
| finished, pipeline red (#396) | 1 | 3.03 M | USD 1.78 reported |
| ended on the limit of 50 turns | 7 | 26.89 M | about USD 15.7 estimated |
| refused: the agent called `web.fetch`, which the frame denies | 3 | 2.81 M | about USD 1.6 estimated |
| **all coding steps** | **15** | **40.78 M** | **about USD 23.8** |

**About USD 12 per merged pull request**, for two changes of about 100 added lines each. Two
thirds of all tokens went to runs that ended on the turn limit and lost their work. The limit is
150 turns on the instance since DEC-0193; no run has reached the coding step since.

The three refusals have one cause in the worker. It offers the agent every tool it knows
(`--tools` lists `WebFetch` too) and approves only the frame's tools (`--allowedTools`). The agent
sees a tool it may not use, calls it, and the worker ends the assignment as the contract requires
(W-07). A tool the frame denies should not be offered.

### 2.3 Where the tokens of a turn come from

Three local calls of Claude Code 2.1.292 with Haiku 4.5, the worker's tool set, and no user
configuration (`--setting-sources project --strict-mcp-config`):

| Measurement | Result |
|---|---|
| One turn in an empty directory: the agent's own instructions and tool definitions | 14 688 tokens |
| One turn in this repository: the same, plus `CLAUDE.md` and the repository's state | 22 094 tokens |
| The P-03 assignment for #256, run as the worker runs it, stopped after 15 turns | context grows from 21 578 to 39 950 tokens, about 1 300 per turn; 30 534 tokens written to the cache, 425 696 read from it, 7 675 output; USD 0.14 |

Three findings follow.

1. **The fixed part is small against the growing part.** The agent's own prefix is about 22 000
   tokens, of which `CLAUDE.md` and the repository's state are about 7 400. Every turn adds what
   the last tool returned. Turn 50 then sends about 85 000 tokens. The instance's runs averaged
   about 70 000 per turn (DEC-0193). Over a run, the cost of reading the cache grows with the
   square of the number of turns.
2. **The agent writes its cache with a lifetime of one hour.** Locally every cache write was
   `ephemeral_1h`, which costs twice the input price; a read costs a tenth. Whether the instance,
   which uses an API key, gets the same lifetime was not measured.
3. **On the instance, cache writes carry most of the money.** Solving the three finished runs of
   version 8 for the split, with Haiku 4.5's prices and the one-hour lifetime:

   | Run | `tokens_in` | Cache writes (derived) | Share of the money that is cache writes |
   |---|---|---|---|
   | #280 | 2.53 M | 0.46 M | 76 % |
   | #388 | 2.31 M | 0.58 M | 77 % |
   | #396 | 3.03 M | 0.69 M | 77 % |

   Locally, writes were 7 % of the input and 43 % of the money. On the instance they are 18 to
   23 % of the input. New text enters the context five to eight times more per turn there:
   large files, long command output, or a cache that was rewritten. The ledger cannot say which,
   because it records only the sum. This derivation assumes the one-hour lifetime; with five
   minutes the writes would be larger still.

**What this means for the owner's claim.** Taktus's own steps cost nothing in tokens. Shortening
the assignment text saves about 1 % directly. Removing `CLAUDE.md` from the agent's context saves
about 3 to 4 % directly: 7 400 tokens written once and read on every turn. The money lies in the
number of turns and in what each tool call brings into the context. Both depend on what the agent
is told to do and on what it can verify.

## 3. The market

### 3.1 Who does what

| System | What the orchestrator provides | What the agent does itself | How the agent is briefed |
|---|---|---|---|
| Claude Code, headless (`claude -p`) | a task, permissions, a turn limit, a money limit (`--max-budget-usd`), structured output (`--json-schema`) | exploring, editing, running checks, subagents with their own context | `CLAUDE.md` from the directory and its parents; `--bare` loads nothing and takes context only from flags such as `--append-system-prompt-file`; the documentation recommends `--bare` for scripted calls |
| OpenAI Codex cloud | a container, a setup script with network, an agent phase without network by default, a proxy | edit, run checks, repeat until they pass | `AGENTS.md`, nearest file wins, at most 32 KiB by default |
| GitHub Copilot coding agent | issue to branch to pull request, an environment on the platform's runners, a firewall for the agent's shell, at most 59 minutes | research, plan, edit, test, commit | `copilot-instructions.md`, `AGENTS.md`, setup steps |
| Devin | a saved machine with tools installed | the whole task | "knowledge" retrieved when relevant, "playbooks" given upfront |
| Cursor cloud agents | an isolated machine, a branch, a pull request, hooks, network rules | the whole task | rules files, `AGENTS.md` |
| Google Jules | a cloud machine, a setup script | a plan the user approves, then the change | `AGENTS.md` |
| Factory | `droid exec` for pipelines | the whole task | `AGENTS.md` |
| Aider | a repository map of about 1 000 tokens, built by parsing the code | edits the files it is given | the map plus the files the user adds |
| mini-swe-agent | a shell and a loop of about 100 lines | everything, with shell commands only | a short system prompt |

The common split: the outside system gives the task, a prepared environment with the tools
already installed, the network policy, the secrets, a time and money limit, and it opens the pull
request. The agent explores, plans, edits, runs the checks and repeats until they pass. Copilot and
Codex separate a setup phase with network from an agent phase without it. No system in the table
asks the agent to read the organisation's governance.

### 3.2 What the evidence says about scaffolding

- Anthropic reached 49 % on SWE-bench Verified in January 2025 with "a prompt, a bash tool and
  an edit tool", keeping the scaffold minimal on purpose.
- On the bash-only leaderboard of February 2026, every model runs in mini-swe-agent with the same
  prompt. The best scored 76.8 %, within a few points of the heavily built agents.
- Agentless, a fixed pipeline with no agent loop, solved 27 % of SWE-bench Lite in 2024 at
  USD 0.34 per issue.
- Reading: with current models, more tooling around the agent adds little. What still adds is
  context management, a way to verify, and a prepared environment.

### 3.3 What the evidence says about instruction files

- An ETH Zurich study of `AGENTS.md` files (arXiv 2602.11988, ICLR 2026) ran Claude Code, Codex
  and Qwen Code on 438 tasks. Files written by a model lowered success slightly and raised cost by
  about 20 %, with 2.5 to 3.9 more steps per task. Files written by developers raised success by
  about 4 points and cost by up to 19 %. The agents follow the instructions, and following them
  means exploring more. Overviews of the repository did not help. The authors recommend only
  minimal requirements, such as the tools to use.
- Claude Code's documentation: a `CLAUDE.md` should stay under 200 lines; longer files lower
  adherence. Knowledge needed only sometimes goes into skills, loaded on demand. A rule that must
  always hold becomes a hook, because a hook is deterministic and an instruction is advice.
- Anthropic's context engineering guide (September 2025): retrieve just in time through file
  names and tools rather than load upfront; recall falls as the context grows ("context rot",
  confirmed for 18 models by Chroma in July 2025).
- The number of instructions a model can follow at once is limited. At 500 simultaneous
  instructions the best model followed 68 % (IFScale, 2025).

This repository's `CLAUDE.md` has 339 lines and governs sessions. The coding worker reads all of
it on every task.

### 3.4 Prompt caching

| Provider | Cache write | Cache read | Lifetime |
|---|---|---|---|
| Anthropic | 1.25 × input for 5 minutes, 2 × for 1 hour | 0.1 × input (less on the newest models) | 5 minutes or 1 hour, counted from the request |
| OpenAI | free up to GPT-5.5; 1.25 × from GPT-5.6 | 0.1 × on new models, 0.25 to 0.5 × on older ones | about 5 to 10 minutes, extendable to 24 hours |

Haiku 4.5, the coding agent's model on the instance, costs USD 1 per million input tokens,
USD 2 for a one-hour cache write, USD 0.10 for a cache read and USD 5 for output. The pricing page
lists Haiku 5.5 at USD 0.10 input and USD 0.50 output for prompts up to 100 000 tokens: a tenth.
A cache pays from its first read. A byte that changes near the start of the context invalidates
everything after it.

### 3.5 Compression and terse output

| Approach | What it changes | Claimed saving | Evidence |
|---|---|---|---|
| caveman ("Say Less") | the agent's answers: short sentences, answer first | output 63 to 20 tokens per answer; 33 % fewer input tokens per session | the project's own benchmarks, no replication; one session 9.9 % worse; its "Auto" part sends data to the vendor's cloud |
| caveman ("Read Less"), headroom | tool output, logs, JSON, files, history before they reach the model | headroom: about 20 % for coding agents, 42 % for exploring code, 60 to 95 % for JSON | the projects' own; headroom keeps originals locally and lets the model fetch them back; runs as a library, a local proxy or an MCP server; Apache-2.0 |
| Masking old tool output (Lindenbauer et al., 2025) | old observations are replaced by a placeholder | cost halved against the raw agent, solve rate equal or slightly higher | peer-reviewed workshop paper, five model configurations, SWE-agent and OpenHands |
| SWE-Pruner (2026) | a small model removes irrelevant lines of tool output | 23 to 54 % fewer tokens, success rate equal or higher | paper, SWE-bench Verified |
| LLMLingua-2, LongLLMLingua | drops tokens from a prompt | 2 to 5 times shorter | measured on question answering, not on code; lossy and not reversible |
| Chain of Draft (2025) | reasoning in steps of about five words | as little as 7.6 % of the reasoning tokens at equal accuracy | paper, arithmetic and logic tasks |

### 3.6 Machine formats and human text

- Forcing a model to answer in strict JSON measurably lowers its reasoning, while it helps
  classification ("Let Me Speak Freely?", EMNLP 2024). Answering freely first and converting
  after reduces the loss. Anthropic advises a short explanation field rather than reasoning inside
  the schema.
- Compact formats for model input, such as TOON, save tokens on uniform tables. An independent
  paper (2026) found plain JSON the most accurate to generate.
- For human text there are standards. ISO 24495-1:2023 sets four principles: the reader gets
  what they need, finds it, understands it, and can use it. It ranks testing with readers above
  readability formulas. The European Commission's "How to write clearly" gives ten rules in every
  EU language. German distinguishes *Einfache Sprache* (complete content, plain text, DIN ISO
  24495-1) from *Leichte Sprache* (core content only, one statement per line, DIN SPEC 33429).

## 4. Findings

1. **Taktus already keeps what it must keep.** Admission, the claim, reading the issue, reserving
   record numbers, writing the branch, the pipeline's verdict, the title, the closing section,
   the labels and giving the claim back are rules or connector calls. They cost no tokens. They
   are where the outward effects, the exactness and the provenance live (ADR-0007, ADR-0014,
   ADR-0024, ADR-0095, ADR-0097). Each was moved there after a failure of the agent: DEC-0025
   found four of five refused descriptions failing on deterministic parts asked of the agent.
   **None of these should move to the worker.**
2. **The assignment asks the agent to do the work of a session.** "Whatever the contribution
   documentation requires" makes a coding agent read doctrine written for sessions that decide,
   record and report. The market gives agents a task, a prepared environment and a few hard
   requirements. The evidence says that broad instructions cost about 20 % more and do not raise
   success.
3. **The agent is asked to verify without the means to verify.** The workspace has no `make`,
   `uv` or `pytest`. Every system in the market prepares the environment before the agent starts.
   A way to verify is what Anthropic's own guidance names first.
4. **Lost work dominates the cost.** Seven of fifteen coding steps ended on the turn limit and
   used 66 % of the tokens. Three ended on a tool offered and then refused. The cheapest saving
   is a run that does not fail.
5. **What costs money inside a run is new text in the context, multiplied by the number of
   turns.** Cache writes carried about three quarters of the money of a finished run. The ledger
   cannot show this, because `tokens_in` sums three prices into one number.
6. **The owner's claim holds for the inside of the step, not for its outside.** The agent should
   choose how to explore, which checks to run, how to edit and how to describe its change. It
   should not hold the outward effects, the verdict or the shape of what a person reads. That is
   the line the adapter obligation already draws: the run writes outward, never the worker.
7. **Terse internal language helps little where it is safe and is dangerous where it would help
   most.** Output is 7 to 11 % of a finished run's money on the instance; a terse voice saves a part of that. Compressing
   tool output targets the cache writes, the largest share, and has the strongest evidence
   (masking halves cost at equal success). Compressing what a person reads, or what the ledger
   and provenance hold, would break principles 7, 12 and 13.

## 5. Recommendation

### 5.1 The line between Taktus and the worker

| Concern | Who holds it | Why |
|---|---|---|
| whether the issue may be taken, the claim, giving it back | Taktus, rule and connector | a fixed set of conditions; an effect outward (ADR-0097) |
| what must be achieved, how it is verified, where the boundary lies | Taktus hands it over verbatim from the issue | the issue is the system of record |
| hard constraints: no workflow files, no secret, no git, no new register record without a number | Taktus states them in a few lines **and checks them with a rule step** on the changeset before the branch is written | an instruction is advice, a check is a verdict; the repository's hooks and gates already exist |
| exploring the repository, choosing files, editing, running checks, repeating | the worker | multi-step work with tools, which the market and the evidence leave to the agent |
| the environment: the repository's tools installed | the operator, through the worker's image or a setup command | every system in the market prepares it; the agent cannot verify otherwise |
| the verdict on the change | the pipeline, read by a rule | never the worker's opinion (ADR-0014) |
| the facts of the change: what changed, why, what was checked, what could not be | the worker, as **fields of a structured result** | the worker knows them; a schema makes them checkable |
| the description a person reads | Taktus, by a template from those fields, in the shape and language the organisation configured | the form is the customer's; a template is reproducible (M1.11) |
| writing the branch, reserving numbers, opening the pull request, labels | Taktus, connector | the run writes outward, never the worker (ADR-0007, ADR-0095) |
| merging | a person | the frame of P-03's level 4 |

### 5.2 How the worker is briefed

1. **A task contract of five parts**, not eight criteria:
   - the goal and the issue's sections "What must be achieved", "How it is verified" and "Where
     the boundary lies", verbatim;
   - the hard constraints, one line each;
   - the command that verifies a change in this repository, if it has one that runs in the
     workspace;
   - the result's schema: summary, files changed and why, checks run with their outcome, checks
     not run with the reason, anything a reviewer must know;
   - nothing about the shape of a pull request description.
2. **A short brief for coding agents**, separate from the session doctrine. The repository's
   coding-agent file (`AGENTS.md`, issue #407) states the tools, the commands, the layout and
   the few rules a change must satisfy, in under 150 lines. `CLAUDE.md` stays what it is: doctrine
   for sessions. The worker starts the agent so that it loads the brief and not the doctrine (for
   Claude Code: `--bare` with the brief as an appended system prompt). A gate keeps the brief
   short and consistent with `CLAUDE.md`.
3. **On demand, not upfront.** The brief names where further rules are written. The agent reads
   them when a task touches them.
4. **A stable prefix.** The brief and the agent's own instructions come first and never change
   within a task. The provider's cache then serves them at a tenth of the price for every turn.
   Nothing changing, such as a time or a run identifier, is placed before them.
5. **Turns and money.** The run's money budget is the bound that holds (ADR-0005). The turn limit
   is a safety bound well above a normal task, as DEC-0193 set it. A run that reaches it stops at
   its boundary and can be resumed (#380), so that work is not lost.
6. **Only the tools the frame allows are offered.** This removes the refusals of section 2.2.

### 5.3 Machine language inside, the customer's language outside

- **Safe to make terse or compressed:** the worker's own conversation with its model, tool output
  before the model reads it, the agent's reasoning, and messages between two machines that no
  person reads. These stay inside the worker adapter. They are not part of the provenance record,
  which holds what the step consumed and produced, not how the agent talked to itself (ADR-0021).
  A compression there must run locally, inside the worker's unit; a service that sends the
  context elsewhere breaks principle 11.
- **Never compressed:** the ledger, the provenance record, the step's reason, the result fields
  a template turns into human text, and anything a person reads: a pull request, a comment, a
  decision request, a report, an explanation (UC-6.5).
- **Structured between machines, prose for people.** The worker returns fields; Taktus renders
  them. The worker writes its fields in plain sentences, not in a compressed voice, because they
  become human text. A field asks for a fact, not for reasoning, which avoids the loss "Let Me
  Speak Freely?" measured.

### 5.4 Principles of human understanding as a product capability

Taktus already holds pieces of this for its own project: `CLAUDE.md` §10 (one idea per sentence,
no term before it is explained, no metaphor where a definition belongs), the reporting levels
(ADR-0029, ADR-0063), the phrasebooks of the owner's channel (ADR-0069), the rendered guides
(ADR-0065), and UC-6.5's requirement that language and depth follow the reader's role.

The proposal is a **writing standard** the product ships as a default, per language:

- the four principles of ISO 24495-1, and §10's three rules as their concrete form;
- the reader's role, language and level (for example *Einfache Sprache*) as configuration of the
  organisation, the way a phrasebook is configured;
- applied in two ways: as the instruction every `llm` step receives when its output is read by a
  person, and as **rule checks** on the result, which are reproducible: sentence length, terms
  used before they are defined, figures not taken from the records (UC-6.5 already requires this
  check), characters the organisation excluded;
- reduced or replaced by the organisation, never emptied, as the anchors are.

A customer then starts from a tested default, not from zero.

### 5.5 Where caveman and headroom fit

- **caveman's terse voice:** not for anything a person reads. Inside the worker it would save a
  part of the output tokens, at most a few per cent of a run's money, at a risk to the quality of
  the result fields. Not recommended as a first step. Its cloud part is excluded by principle 11.
- **headroom's compression of tool output:** fits inside the worker, locally, behind the model
  adapter of the worker. It targets the cache writes. The expected saving is 20 to 40 % of the
  input money, at equal success where the papers measured it. It must be measured on Taktus's own
  tasks first (issue #408's fixed evaluation cases), because the evidence is mostly the project's
  own. The simplest form, masking old tool output, needs no third-party code and has the best
  evidence.
- **LLMLingua-style token dropping:** not for code. It is lossy and was measured on question
  answering.

## 6. Risks

- **Quality.** A shorter brief can miss a rule the pipeline then fails. The pipeline catches it;
  the cost is one more run. The rule steps of 5.1 catch the hard constraints before the branch.
- **Reproducibility.** The worker's step stays `tolerant`. Nothing of this plan makes a variable
  method produce an exact result.
- **Auditability.** Compression inside the worker is invisible in the ledger. The worker records
  in the step's provenance whether compression ran and in which version, so that a result can be
  traced to the configuration that produced it.
- **Lock-in.** `--bare` and an appended system prompt are Claude Code's options. The brief itself
  is a plain file that every agent in section 3.1 reads; only the worker adapter knows how to pass
  it.
- **The evidence is thin in places.** caveman's and headroom's figures are their own. The
  instance's split of cache writes is derived, not recorded. The local measurement covers 15
  turns of one task.

## 7. The staged plan

The plan fits DEC-0197's stages. Stage 0 measures ten handed tasks, at least 80 % merged without
rework, and money per merged pull request below an agreed figure. Each change below is measured on
the stage-0 tasks before the next.

| # | Change | Expected effect | What it needs |
|---|---|---|---|
| 1 | The worker offers only the tools the frame allows | the three `web.fetch` refusals of 72 hours disappear: about 7 % of all tokens | plain work, an issue; a bug fix of the worker |
| 2 | The ledger records cache writes, cache reads, plain input and turns apart, per step | the split of 2.3 is measured, not derived; the money per step is priced exactly | an additive field of the worker's consumption; an ADR amendment of the budget's consumption if the contract changes (M3.5 only if it breaks) |
| 3 | A run that reaches the turn limit stops at its boundary (#380) | no lost work; with 150 turns, the 66 % share of lost tokens falls towards zero | plain work, already an issue |
| 4 | The worker's environment carries the repository's check tools, or a setup command installs them | the agent verifies before the pipeline does; fewer red pipelines and repeated runs | plain work in the worker image or the operator's values (ADR-0090); a dependency of the worker image is tier 2, not M3.8 |
| 5 | P-03 version 10: the task contract of 5.2, a result schema, the description rendered by a template, rule steps for the hard constraints on the changeset | fewer turns spent reading doctrine and the template: expected 20 to 40 % fewer turns per task | plain work (M1.11 for where the text is produced); a change of the bundle |
| 6 | A coding-agent brief (`AGENTS.md`, #407) loaded instead of `CLAUDE.md` | about 3 to 4 % directly; about 20 % if the ETH study's effect holds here | plain work; `CLAUDE.md`'s first standing order applies to keeping both consistent |
| 7 | Masking or compressing old tool output inside the worker, measured on fixed cases (#408) | 20 to 50 % of the input money, if Taktus's tasks behave as the papers' | an ADR: what a worker may do to its own context, that it runs locally, and that the provenance names it |
| 8 | A calibration of the coding agent's model on the fixed cases: Haiku 4.5 against a newer, cheaper or stronger model | possibly a tenth of the price per token, or fewer turns per task | the owner: binding a purpose to a model (M3.12, M3.14); spending on the calibration beyond USD 1 (M3.10) |
| 9 | The writing standard of 5.4 as a product capability | every customer starts from a tested default; human text is checked by rules | the owner: accepting the feature (M3.2) and what the use case requires (M3.15); then an ADR |

**What the money per merged pull request could become.** The measured figure is about USD 12. A
run that does not fail costs USD 1.2 to 1.8 today (2.2). With changes 1 to 3 the failures that
lost work disappear, and the figure approaches the cost of one finished run plus the occasional
repeat: an estimate of USD 2 to 3. Changes 5 to 7 together could lower one run by a third to a
half: USD 1 to 2 per merged pull request. Change 8 could lower it further. These are estimates;
each change is measured on the stage-0 tasks before the next is taken.

## 8. Open questions for the owner

These are proposals. The session that receives this file raises each as a request where the
anchors require it.

1. **The figure for money per merged pull request in stage 0** (DEC-0197 left it to the first
   measurements; M3.10).
   - A: USD 3, lowered once change 5 is measured. *Recommended:* it is reachable after changes 1
     to 3 and still a real bound.
   - B: USD 5, the run's limit today.
   - C: USD 1.5, the cost of one finished run today.
2. **A calibration of the coding agent's model** (M3.12, M3.14, and M3.10 for the spend).
   - A: run the fixed cases of #408 on three models — Haiku 4.5, a newer Haiku, a Sonnet — for at
     most USD 15, then choose by money per passed case. *Recommended:* the price per token differs
     by a factor of ten, and a stronger model may need fewer turns.
   - B: keep Haiku 4.5 until stage 1.
3. **Compression of tool output inside the worker** (an ADR the owner should see, since it
   changes what the model reads).
   - A: allowed, local only, reversible, recorded in the provenance, after it was measured on the
     fixed cases. *Recommended.*
   - B: masking of old tool output only, no third-party compressor.
   - C: none.
4. **A writing standard as a product capability** (M3.2, M3.15).
   - A: ship a default per language, built on ISO 24495-1 and §10, with rule checks, configurable
     per organisation and never emptied. *Recommended:* it is what lets a customer start from a
     tested default, and the checks make it reproducible.
   - B: a recommendation in the documentation only.
   - C: leave it to each organisation.

## 9. Sources

All web sources were read on 2026-10-14 unless a date is given.

**Repository and instance.** `blueprints/dev-orchestration/processes/P-03-implementation.yaml`
(version 9); `workers/claudecode/worker.py` and `README.md`; `docs/runs/2026-10-12-the-second-live-run.md`;
`docs/runs/2026-10-13-the-instance-opens-its-own-pull-request.md`; DEC-0019, DEC-0025, DEC-0193,
DEC-0197, DEC-0198; ADR-0005, ADR-0007, ADR-0014, ADR-0021, ADR-0024, ADR-0029, ADR-0030,
ADR-0053, ADR-0065, ADR-0069, ADR-0095, ADR-0097; UC-6.5; the instance's ledger, 72 hours to
2026-10-14 08:12 CEST, read by the monitor job of DEC-0197.

**Local measurement.** Claude Code 2.1.292, model Haiku 4.5, three calls: one turn in an empty
directory, one turn in this repository, 15 turns of P-03's assignment for #256 in a copy of
`main` at `141ed3b`. List price USD 0.20 in all.

**Coding agents.**
- Claude Code headless mode: https://code.claude.com/docs/en/headless
- Claude Code memory and `CLAUDE.md`: https://code.claude.com/docs/en/memory
- Claude Code best practices: https://code.claude.com/docs/en/best-practices
- Claude Code subagents: https://code.claude.com/docs/en/sub-agents
- How Claude Code works: https://code.claude.com/docs/en/how-claude-code-works
- Codex `AGENTS.md`: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Codex cloud environments: https://developers.openai.com/codex/cloud/environments
- GitHub Copilot coding agent: https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent
- Its firewall: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-firewall
- Devin: https://docs.devin.ai/onboard-devin/snapshots
- Cursor cloud agents: https://cursor.com/docs/cloud-agent
- Google Jules: https://jules.google/docs/
- Factory `droid exec`: https://docs.factory.ai/droid-exec/overview.md
- Aider repository map: https://aider.chat/docs/repomap.html
- mini-swe-agent: https://github.com/SWE-agent/mini-swe-agent
- `AGENTS.md` standard: https://agents.md/

**Scaffolding and context.**
- Anthropic, SWE-bench with Claude 3.5 Sonnet (6 January 2025): https://www.anthropic.com/research/swe-bench-sonnet
- SWE-bench bash-only (February 2026): https://www.swebench.com/bash-only.html and https://simonwillison.net/2026/Feb/19/swe-bench/
- Agentless (July 2024): https://arxiv.org/abs/2407.01489
- Anthropic, effective context engineering (29 September 2025): https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic, building effective agents (19 December 2024): https://www.anthropic.com/engineering/building-effective-agents
- Gloaguen et al., evaluating `AGENTS.md` (arXiv 2602.11988): https://arxiv.org/abs/2602.11988
- Chroma, context rot (14 July 2025): https://research.trychroma.com/context-rot
- IFScale, how many instructions models follow (arXiv 2507.11538): https://arxiv.org/abs/2507.11538

**Prices.**
- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- OpenAI prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching
- OpenAI pricing: https://developers.openai.com/api/docs/pricing (the page itself refused the reader; figures from this mirror)

**Compression and formats.**
- caveman: https://github.com/JuliusBrussee/caveman
- headroom: https://github.com/headroomlabs-ai/headroom
- Lindenbauer et al., the complexity trap (arXiv 2508.21433): https://arxiv.org/abs/2508.21433
- SWE-Pruner (arXiv 2601.16746): https://arxiv.org/abs/2601.16746
- LLMLingua-2 (arXiv 2403.12968): https://arxiv.org/abs/2403.12968
- LongLLMLingua (arXiv 2310.06839): https://arxiv.org/abs/2310.06839
- Chain of Draft (arXiv 2502.18600): https://arxiv.org/abs/2502.18600
- Let Me Speak Freely? (arXiv 2408.02442): https://arxiv.org/abs/2408.02442
- Anthropic structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- TOON: https://github.com/toon-format/toon; Matveev (arXiv 2603.03306)

**Human-facing language.**
- ISO 24495-1:2023, summary by the International Plain Language Federation: https://www.iplfederation.org/the-iso-plain-language-standard-part1
- European Commission, clear writing: https://commission.europa.eu/about-european-commission/departments-and-executive-agencies/translation/clear-writing-europe_en
- DIN, *Leichte* and *Einfache Sprache*: https://www.dinmedia.de/de/themenseiten/leichte-und-einfache-sprache

**Where the evidence is thin.** caveman's and headroom's figures are their own benchmarks. The
leaderboard's cost per task could not be read. Factory's limits and Sweep's state were found only
in secondary sources and are left out. The instance's split of cache writes is derived from money
and an assumed cache lifetime.
