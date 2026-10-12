# What Taktus takes from four products, and what it leaves — 2026-10-12

**Why this file exists.** The owner asked a session to look at the market as a product owner. The
products were the ones the owner named: Zenkit, the ServiceNow AI Platform, LiteLLM and OmniRoute.
The task was to take over only what fits Taktus's vision. The owner accepted every proposal
(DEC-0190). The issues that carry the proposals name this file as their source, and the screens
they describe are specified here.

**How it was made.** Web research by three sessions on 2026-10-12. Every claim about a product
cites the page it came from, and the products' text is summarised, never quoted. The ServiceNow
platform page refused automated fetches (HTTP 403), so that part rests on ServiceNow's newsroom,
documentation and filings, and on third-party reports, each of them marked.

**It expires.** Products change. This file records one date. Product names appear here and in
no part of the core (ADR-0003).

**Mapping to the issues.**

| Proposal | Issue |
|---|---|
| F1 value streams | #338 |
| F2 a role at a human step | #331 |
| F3 role profiles | #344 |
| F4 a register of everything that acts | #332 |
| F5 dependency and blast radius | #333 |
| F6 process variants | #334 |
| F7 price import | #327 |
| F7 purpose routing | #328 |
| F7 operator credentials and budgets | #352 |
| F8 connectors in their own images | #339 |
| F8 the catalogue with tiers | #348 |
| F9 rehearsal from the plan dialogue | #329 |
| F9 stage view | #335 |
| F9 input check | #336 |
| F9 outside participants | #337 |
| F9 what a person may ask for | #340 |
| F9 BPMN import and export | #345 |
| F9 A2A binding | #349 |
| The adapter's cache-write gap | #312 |

---

# Part 1 — Zenkit

## 0. The owner's memory, checked

The owner remembers that Zenkit moves away from org charts and silos towards processes along the value chain,
and derives positions ("Stellen") from those processes.

**Verdict: the idea is Zenkit's marketing and educational content. It is not a product feature.**

- **Present as an idea, in content.**
  - The glossary entry *Prozessorganisation* defines process organisation as shaping a company by its
    business processes instead of its departments. Responsibilities, interfaces and information flows follow
    the processes. Source: https://zenkit.com/de/glossar/prozessorganisation/
  - The blog post on process management in 2026 argues three points. Silos are the brake. One process owner
    should carry end-to-end responsibility across departments. Roles should follow from processes, not from
    the hierarchy. The post names no Zenkit feature. Source: https://zenkit.com/de/blog/prozessmanagement-2025/
  - Zenkit's blog describes the process map ("Prozesslandkarte") in four bands: management, core, support, and
    optimisation/analysis processes. Customer need is on the left and customer outcome on the right.
    Source: https://zenkit.com/de/blog/prozesslandkarte/
  - The blog also describes the value-chain diagram (WKD), which splits processes into management, core and
    support processes. Source: https://zenkit.com/de/blog/prozessmodellierung/
  - The glossary explains value stream mapping and links it to building a process in Zenkit.
    Source: https://zenkit.com/de/glossar/value-stream-mapping-vsm/
  - The silo argument also appears in Zenkit's own search-result summary of that content.
    Source: https://zenkit.com/de/blog/prozessmanagement-2025/
- **Absent from the product pages.** None of these pages offers an org chart, a value-chain object, a position
  or job profile, or any derivation of positions from processes:
  - features: https://zenkit.com/de/funktionen/
  - enterprise: https://zenkit.com/de/unternehmen/
  - solutions: https://zenkit.com/de/loesungen/
  - BPM: https://zenkit.com/de/geschaeftsprozessmanagement/
  - The glossary has no entries for value chain, org chart, position or role: https://zenkit.com/de/glossar/
  - Roles appear only as BPMN pools and lanes, and as access roles: https://zenkit.com/de/geschaeftsprozessmanagement/
- **Consequence.** Generating positions from processes is not something a competitor ships. For Taktus it is
  open ground (section 3).

---

## 2. Ideas that fit Taktus, and ideas that do not

### 2.1 Checked and dropped

| Zenkit idea | Why it does not fit |
|---|---|
| Combined inbox for process and project tasks | A Taktus-owned task list beside the ticket system breaks principle 1, which the vision names as the typical creeping violation. Taktus sends work into the tool where the person already works (UC-1.1, UC-5.3) and batches decision requests per decider (`throughput.md` §5). |
| Kanban, Gantt, wiki, mind map, chat, file system | Each one is a second system of record (P1; `non-goals.md`, "not a tool landscape"). |
| Own form builder (Zenforms) | Same reason. A form is a connector capability that starts a process (UC-4.14). Taktus does not build one. |
| Drag-and-drop BPMN as the primary way to build | The non-goal "not a visual block builder as the primary interface" excludes it, and so does P2, which forbids a person assembling the process while the AI fills blanks. A diagram is derived from the version and never used to edit it (UC-4.2). |
| Supervisor persona as a person who watches people | P14. Supervision in Taktus is of processes (level 3, "human on the loop", UC-7.1), never of employees. |
| Per-user seat pricing | Not a product idea. It also clashes with the Takt as the unit of accounting (ADR-0010). |
| "Made in Germany" as a marketing line only | Taktus must generate its compliance claims from the real configuration (P11). It cannot simply assert them. |

### 2.2 Ideas that fit

Every idea below names:

- what it is at Zenkit
- how it would look in Taktus
- which use case it extends, or which gap it fills
- its effect on autonomy and anchors
- how it meets P14
- its value across the customer spectrum
- the effort: S, M or L
- its risks

#### Idea A — The process map: management, core, support

- **At Zenkit.** Education content only: the four-band process map and the value-chain diagram. Sources:
  https://zenkit.com/de/blog/prozesslandkarte/ and https://zenkit.com/de/blog/prozessmodellierung/
- **In Taktus.**
  - Add a classification to the process version: `kind: management | core | support`.
  - Add the same classification to the chain object of UC-15.4.
  - Store it in the bundle (ADR-0011), so that it is versioned like everything else.
  - The `reporting` component draws the map from it. The map is derived and stored nowhere else, under the
    same rule as UC-4.2.
- **Use cases.**
  - Extends UC-9.2: departmental maturity gets a second axis, maturity per core value stream.
  - Extends UC-15.1: a blueprint declares the kind of each of its processes.
- **Autonomy and anchors.** None directly. The kind is a description, not a frame.
- **P14.** Nothing person-related.
- **Value.**
  - Family: low.
  - SME: medium, because it is the first picture of "what we do".
  - Corporation: high, because process maps are standard in BPM and ISO 9001 practice.
  - Operator: high, as a blueprint attribute.
- **Effort.** S.
- **Risks.**
  - The classification is subjective, so it must stay configuration and never be computed.
  - Two classifications must not drift apart: one on the chain and one on the process. P7 forbids two numbers for
    the same thing.

#### Idea B — Human steps name a role (BPMN lanes, but derived)

- **At Zenkit.** Pools and lanes assign process parts to departments or roles. Source:
  https://zenkit.com/de/geschaeftsprozessmanagement/
- **The gap in Taktus.**
  - `contracts/shared/v1/Step.json` has no field saying which role performs a `human` step.
  - A `fallback` reads `to: human` with no role.
  - Roles exist only on anchors (`Anchor.json`, a role decides) and on checks (`Check.json`, approval and sampling
    by role).
  - So today nobody can say from the process alone who has to act.
- **In Taktus.** A contract change, which needs an ADR and must pass `make gate-contracts`:
  - `Step.role` is required for `human`. It names a role of the organisation's structure, never a person.
  - `Fallback.role` is required when `to: human`.
  - The run resolves the person at runtime, the same way as for anchors.
  - The takeover instructions (UC-6.3) already name "the expertise each part needs". That expertise becomes
    structured: `expertise: [..]` per step.
- **Use cases.**
  - Fills the gap behind UC-6.7, which counts a role "where a process's takeover instructions require it".
    Today that is free text.
  - Fills the gap behind UC-9.3, whose revert analysis needs "the roles needed".
  - Feeds idea D.
- **Autonomy and anchors.**
  - At level 2, the confirmations go to the step's role, not to whoever started the run.
  - Anchors are unchanged.
- **P14.** Roles only. UC-7.3 already forbids granting a right to a person outside a role.
- **Value.**
  - Family: low.
  - SME: high, because "who has to act" becomes visible.
  - Corporation: high.
  - Operator: medium.
- **Effort.** M: contract, ADR, bundle parsing, run resolution and examples.
- **Risks.**
  - A role held by one person makes a role-level figure identify that person. The withholding rule of NTC-0168
    must extend to role sums.

#### Idea C — The value stream as the owned, end-to-end unit

- **At Zenkit.** The process owner carries end-to-end responsibility across departments to break silos. Source:
  https://zenkit.com/de/blog/prozessmanagement-2025/
- **In Taktus.**
  - UC-15.4 already declares a chain object: order to cash, procure to pay, incident to resolution.
  - Extend the chain to be the value stream:
    - add `kind` (idea A)
    - add `trigger`, the customer need
    - add `outcome`, the customer result
    - add one **owner role**, a responsibility anchor at the level of the stream (today UC-15.5 anchors only the
      domain)
  - Do not invent a second object.
- **Use cases.**
  - Extends UC-15.4 and UC-15.5.
  - Its figures come from UC-9.1, UC-9.3 and UC-9.5, aggregated per stream.
  - UC-9.3 already promises aggregation per chain.
- **Autonomy and anchors.**
  - Raises inside a stream go to the stream owner, as well as to the domain owner.
  - Who decides when the two disagree is an open point. It is a mode-3 question for the owner, because it
    changes what UC-15.5 requires.
- **P14.** The owner is the addressee of duties, never the subject of a metric. UC-15.5 §3 already says so.
- **Value.**
  - Family: low.
  - SME: medium.
  - Corporation: very high, because silos are a corporation's problem.
  - Operator: high, as a blueprint-level template.
- **Effort.** M. The chain object is still `specified` for 0.7.0, so this belongs there.
- **Risks.**
  - Two owners, domain and stream, can conflict. This needs a decision record before it is built.

#### Idea D — Role profiles derived from processes ("Stellenprofil")

- **At Zenkit.** A stated idea only: roles follow from processes. No product. Sources:
  https://zenkit.com/de/blog/prozessmanagement-2025/ and https://zenkit.com/de/glossar/prozessorganisation/
- **In Taktus.** A generated read model, owned by `value` (ADR-0029 files figures with their owner) and shown by
  `reporting`. Section 3 has the detail.
- **Use cases.** New requirement, so a mode-3 opinion for the owner (DEC-0041). It rests on UC-6.3, UC-6.7,
  UC-9.3, UC-9.5 and UC-7.3.
- **Value.** Section 3.
- **Effort.** L, including the screen.

#### Idea E — BPMN import and export as an open format

- **At Zenkit.** Existing BPMN models are imported and activated. Source: https://zenkit.com/de/prozesse/
- **In Taktus.**
  - **Import.** BPMN is one more *description* for UC-4.1. Taktus reads tasks, lanes and gateways. It then proposes
    a process: a method per step with its reason, lanes as roles (idea B), and level 1 or 2 to start. A person
    commissions it (control-plane §3).
  - **Export.** BPMN is a projection of the version, like the Git mirror (control-plane §4.2), so that an
    organisation can leave with its processes (P13).
  - The method, the exactness and the autonomy statement go into BPMN extension elements.
  - Import and export run in an adapter. The core never names BPMN tooling.
- **Use cases.**
  - Extends UC-4.1, a process from a description.
  - Extends UC-9.4, discovery: a BPMN archive is a source of written-down processes.
  - Extends UC-5.7 and the export of P13.
- **Autonomy and anchors.** An imported process enters at level 1 or 2, as a discovered one does (UC-9.4).
- **P14.** Lanes that name persons are mapped to roles on import, or refused.
- **Value.**
  - Family: none.
  - SME: medium.
  - Corporation: high. Many corporations have BPMN repositories, and migrating them is a sales argument.
  - Operator: medium.
- **Effort.** M for import, M for export.
- **Risks.**
  - BPMN cannot express method, exactness or fallback, so export is lossy unless extensions are used.
  - Import must never become "the diagram is the builder". It ends in a proposal, not a version.

#### Idea F — Test a process immediately ("start/stop")

- **At Zenkit.** Processes are tested right away instead of after weeks of implementation. Source:
  https://zenkit.com/de/prozesse/
- **In Taktus.**
  - The rehearsal mechanism already exists (ADR-0030): outward operations answer from recordings.
  - Offer it to the person in the plan dialogue as a "rehearse this version" act before commissioning.
  - Show the run live (UC-6.10) and show the exactness statement (UC-6.9).
- **Use cases.** Extends UC-1.2, planning in dialogue, and UC-4.3, new versions.
- **Autonomy and anchors.** A rehearsal acts on nothing, so no anchor fires for real. The anchor is shown as
  "would halt here".
- **P14.** Not affected.
- **Value.** High for every segment, because it lowers the fear of the first run.
- **Effort.** S to M. The mechanism exists; the user-facing act does not.
- **Risks.** A rehearsal is only as good as its recordings. A first run with no recording must say so.

#### Idea G — External participants without an account

- **At Zenkit.** External people take part through e-mail links or their own task tools. Source:
  https://zenkit.com/de/prozesse/
- **In Taktus.**
  - A `human` step whose role is external, such as a supplier or a client, is answered through the channel the
    external party already uses.
  - It is never answered through a Taktus account.
  - The answer is placed by a single-use link bound to the step, and the act is recorded in the ledger.
- **Use cases.**
  - Today UC-1.7 refuses unknown senders, and UC-1.9 only triages them.
  - So this is a gap between UC-1.7 and UC-15.3, the partner interfaces.
- **Autonomy and anchors.** An external answer is never treated as an anchor decision of the organisation.
- **P14.** External persons appear by their role in the stream ("supplier"), not by name, in every figure.
- **Value.**
  - Family: medium, for example a tax adviser.
  - SME: high.
  - Corporation: high.
  - Operator: medium.
- **Effort.** M.
- **Risks.**
  - It touches identity and security, so the threat model must be part of the ADR.
  - Placement by a link must not turn into "a matching address links someone", which control-plane §2 forbids.

#### Idea H — Budgets per group, shown the way Zenkit shows them

- **At Zenkit.** A credits budget allocated per group, with a "62 % of 25,000 used" style display. Source:
  https://zenkit.com/de/ki/
- **In Taktus.** Already stronger: budgets per unit of `org_path` (UC-8.5), Takt and money (ADR-0010), and
  admission before every step. Only the *presentation* is worth copying: one bar per unit, in the view of the
  person who owns the budget.
- **Value.** Medium for all segments.
- **Effort.** S.
- **Risks.** None beyond P9: show the bar only to its owner and to the roles UC-6.4 entitles.

---

## 3. The value-chain organisation in Taktus

### 3.1 The model

```
tenant
 └─ value stream  (chain of UC-15.4 + kind + trigger → outcome + owner role)      idea A, C
     └─ process   (version: graph, autonomy statement, takeover instructions)     exists
         └─ step  (method, reason, exactness, fallback, role?, expertise?)         idea B
              │
              ├── performed by Taktus: rule · statistics · ml · neural · wait  (reproducible)
              ├── performed by Taktus: llm · worker                            (variable)
              └── performed by a role: human step · anchor · approval check ·
                                       sampling check · fallback → human
```

- **The org chart is not dropped.** `org_path` stays. It governs visibility, sharing and cost (UC-1.4). The value
  chain is a second, orthogonal view.
- **A department boundary becomes an attribute of a handover.** It records where a stream crosses from one unit of
  `org_path` to another. That is the "silo crossing" this view makes visible.

### 3.2 How a role profile is generated

For each role R of the structure, `value` reads data that already exists or is added by idea B. It reads nothing
about any person.

| Section of the profile | Source in Taktus |
|---|---|
| **Purpose.** The value streams R contributes to, and at which stage | streams → processes → steps where R appears |
| **Performs.** The human steps R does, with step, process, stream and the expertise needed | `Step.role`, `Step.expertise` (idea B) |
| **Decides.** The anchors addressed to R, approvals above a threshold, and raises of autonomy | `Anchor.json` role, `Check.json` approval, UC-15.5 |
| **Supervises.** Sampling checks, level-3 processes where R is on the loop, and fallbacks that land on R | `Check.json` sampling, autonomy statement, `Fallback.role` |
| **Must be able to take over.** Automated steps whose takeover instructions name R's expertise, and the systems and credential parameters involved | UC-6.3 instructions |
| **Owns.** The value streams and domains where R is the responsibility anchor | idea C, UC-15.5 |
| **Load, steady state.** Expected hours a month of human steps: count of steps × time per step | runs and ledger; time by hand from the revert analysis, UC-9.3 |
| **Load if Taktus stops.** Hours a month R would carry if the automated steps it must take over ran by hand | revert analysis, UC-9.3 |
| **Waiting at R.** Blocked share of `wait.human` on steps addressed to R | `BlockedTime`, `throughput.md` §1 |
| **Change.** Open proposals that move steps away from R or towards R, such as a decision turned into a rule or a fallback rate rising | UC-4.4, `methods.md` §3, `throughput.md` §5 |
| **Bus factor.** Processes that stand still without R; failed or missing takeover trials | UC-6.7 |
| **Cost rate.** Personnel cost rate per role, for the revert analysis only | UC-9.3 (rate per role; a rate per person cannot be configured) |

**P14 rules that the profile must carry.** These are what the use case would require:

- **Structure versus figures.** Structural facts are always shown: which steps, which decisions, which expertise.
  Time figures (hours, waiting) are withheld when fewer than two persons hold R. This extends NTC-0168 from
  processes to roles. Exception: a person who holds R sees their own times beside the role's (P14 permits; UC-13.5).
- **Dependency, not assessment.** "Processes that stand still without R" is about dependency, and UC-6.7 already
  shows it for a role held by one person.
- **No conclusions about jobs.** The profile states what the processes need. It never states whether a person is
  needed. UC-13.5 §3 already sets this boundary, "not a statement about anyone's job".
- **Workforce planning is the organisation's.** Load figures are a steering input. Any decision that follows from
  them stays with a person and belongs in the strategic anchor set (ADR-0008).
- **Export, but no file per person.** The profile exports as Markdown, PDF or JSON (P7, P13). It can be sent to the
  organisation's HR system through a connector (P1: HR stays the record of positions). It is never stored as
  a person's file.

### 3.3 The screen: "Value chain"

**Where it lives.** A view of `reporting` (UC-6.4). Every figure is read from the component that owns it
(ADR-0029). The view itself is stored nowhere.

**Who sees it.**

- Management, the executive and stream owners see it by default.
- An employee sees it for the streams their roles touch, with their own roles highlighted.

**A. Header**

- The tenant name.
- A period selector: 30 or 90 days, or a quarter.
- A filter by `org_path` unit.
- A toggle, *Show departments*: it overlays department boundaries as tinted vertical bands.
- A toggle, *Simulation*: pick a process and a level, as in UC-9.1. Marked as a simulation everywhere.
- *Export*, as Markdown, PDF or JSON.

**B. Overview: the process map**, a full-width band with three tiers.

- **Top tier: management processes.** Small tiles.
- **Middle tier: core value streams.** Large chevrons, left to right, from the customer need (left edge label) to
  the customer outcome (right edge label). Each chevron shows:
  - name and owner role
  - an autonomy mix bar: share of steps at levels 1, 2, 3 and 4
  - a method mix bar in eight colours, with reproducible shades on the left and variable shades on the right
  - flow efficiency: working time divided by lead time, VSM-style, from runs and blocked time
  - blocked share and the top blocking cause
  - the value-balance quadrant icon (UC-9.3)
  - bus-factor dots: takeover test passed or not, removal test passed or not (UC-6.7)
  - a count of silo crossings, meaning handovers between `org_path` units, and the mean wait at them
- **Bottom tier: support processes.** Small tiles.
- **Click a chevron** to open view C.

**C. Stream detail: the role swimlanes.**

- **Columns** are the processes of the stream, in chain order. A thin column between two processes is the
  handover, showing which items cross (UC-15.4) and the wait at that boundary.
- **Rows (lanes).** Fixed lanes on top, then one lane per role that appears in the stream:
  1. *Taktus — reproducible* (`rule`, `statistics`, `ml`, `neural`, `wait`)
  2. *Taktus — variable* (`llm`, `worker`)
  3. one lane per role, sorted by order of first appearance
  4. *External*: supplier, client or authority (idea G)
- **Cells** hold step chips. A chip shows the step name, a method colour, an exactness letter (E/S/T/F) and its
  glyphs:
  - ⚓ anchor
  - ✓ approval check
  - ◔ sampling check
  - a dashed arrow from a Taktus chip down to a role lane for each fallback to a person
- **Lane header**, per role lane: role name, hours a month of human steps (or "withheld, fewer than two
  holders"), waiting share at this role, and a count of steps it must be able to take over.
- **Department overlay** (toggle): tinted bands behind the columns. Every handover that crosses a band gets a red
  marker. Hovering the marker shows the wait at the crossing.
- **Hover a chip** to see method, reason, alternatives rejected, fallback, exactness, autonomy of the process, and
  the last 30 days' runs and error rate.
- **Click a chip** to open the process diagram at that step (UC-4.2), or the live view if a run is in progress
  (UC-6.10).

**D. Side panel: the role profile.** It opens when a lane header is clicked. It has the sections of §3.2 in this
order:

1. Purpose
2. Performs
3. Decides
4. Supervises
5. Must be able to take over
6. Owns
7. Load, now and if Taktus stops
8. Waiting
9. Change (open proposals)
10. Bus factor
11. Required expertise, as a deduplicated list
12. Systems, by capability

Two buttons:

- *Export as position description draft*: Markdown, carrying a marker that says it was generated from process
  version X on date Y.
- *Send to HR system*: through a connector, and only if one is configured.

There is no button that names, ranks or compares persons.

**E. Personal mode.** A logged-in person sees "My roles" pre-selected. Their own times are shown beside the role's,
and the view links to their contribution view (UC-13.5). Nobody else sees this mode's figures.

**F. Mobile.** The process map becomes a vertical list of stream cards. The stream detail becomes one card per role
with its steps listed. There is no horizontal page scroll.

**Interactions in summary.**

| Gesture | Result |
|---|---|
| Hover a chip | the step's method, reason, exactness and fallback |
| Click a chip | the process diagram, or the live run |
| Click a lane header | the role profile |
| Toggle departments | the org chart overlaid; silo crossings appear |
| Toggle simulation | the hours and waiting a level change would shift between Taktus lanes and role lanes |
| Click a proposal in the profile | the decision request (UC-7.4), addressed to the owner of the stream |

### 3.4 Value across the customer spectrum

| Segment | Value |
|---|---|
| Single person or family | Low to medium. One or two streams, such as household administration or taxes, and roles like "parent" or "tax adviser (external)". Mainly useful as the takeover view: "who in the family must be able to do this if Taktus stops". |
| SME | High. No organisation designer is needed: position descriptions for hiring come from what the processes need, and the risk of a role nobody can take over becomes visible. |
| Corporation | Very high. It makes the process organisation, which consultants sell, visible on operating data. Silo crossings are measured, not workshop-estimated. BPMN import (idea E) feeds it. |
| Operator hosting many tenants | Reference value streams ship in blueprints (UC-15.1). No data is compared across tenants: each tenant is apart (ADR-0020). |

### 3.5 Effort, order, risks

**Order.**

1. Idea B, the role on human steps and fallbacks. M; ADR plus contract change. Without it no profile can be honest.
2. Idea A, the classification. S.
3. Idea C, the chain as value stream with an owner role. M; 0.7.0 with UC-15.4.
4. The profile read model in `value`. M.
5. The screen. L; 0.5.0 views at the earliest, realistically after 0.7.0, once a second domain exists.

**Records needed before building.**

- A mode-3 opinion: a new use case for role profiles, plus the change to UC-15.5 for stream owners.
- An ADR for the step contract change.

**Risks.**

1. **Re-identification.** A role held by one person makes any time figure about that person. The withholding rule
   must cover role sums, and a test must prove it, as UC-13.5 does for its rule.
2. **Co-determination in Germany.** A system "suitable" for monitoring performance falls under works-council
   co-determination (§87(1) no. 6 BetrVG). Taktus's data-model rule helps in that negotiation but does not make it
   unnecessary.
   - This is a reading of German labour law, not legal advice. It belongs with the labour-law review that DEC-0029
     already requires for personnel blueprints.
3. **Misuse as headcount planning.** "Load if Taktus stops" can be read as "people we no longer need". The view
   must state its boundary, as UC-13.5 does.
4. **Principle 1.** HR systems remain the record of positions. Taktus produces a draft, never the position master.
5. **Subjective inputs.** Time by hand per step is an assumption (UC-9.3). Every figure built on it must show who
   set it.

---

# Part 2 — the ServiceNow AI Platform


Product-owner market note. Researched 2026-10-12. Every external claim carries a source number; the
list is at the end. All text is paraphrased.

**Method note.** The starting page `servicenow.com/de/platform.html` refused automated access (HTTP
403, also via plain HTTP client), as did `servicenow.com/platform.html` [S0]. The picture below is
therefore built from ServiceNow's newsroom, its product documentation (`servicenow.com/docs`),
community pages, and third-party reporting. Claims from third parties are marked *(3rd party)*.
`docs/vision/market.md` is stale by its own header; this note can feed its re-establishment, but
is not itself a citeable market statement until checked.

---

## 1. What the ServiceNow AI Platform offers

| Area | What it is | Src |
|---|---|---|
| **AI Agents, AI Agent Studio** | Agents built in a studio and run through their lifecycle (create, test, deploy, monitor, retire). Agentic capabilities came at no extra cost for the top two tiers (Pro Plus, Enterprise Plus) from March 2025. | [S5] [S6] [S4] |
| **AI Agent Orchestrator** | A specialised agent that plans and coordinates a team of agents. It keeps short-term memory and tracks goals. A "dynamic orchestrator" narrows candidates when more than about 8–10 agents are available. Planning uses a ReAct-style prompt. | [S5] [S18] |
| **Supervised / autonomous mode** | Per agent tool: autonomous (runs without input) or supervised (a person approves before the action executes). | [S6] |
| **AI Agent Fabric / Action Fabric** | Agent-to-agent and agent-to-tool communication over MCP and A2A, with partners such as Microsoft, Google Cloud, IBM, Adobe, Zoom (2025). In 2026, "Action Fabric" lets external agents trigger governed actions inside ServiceNow. | [S1] [S16] [S3] *(3rd party)* |
| **AI Control Tower** | Launched May 2025: one place to inventory and govern every AI agent, model and workflow, native or third-party, with GRC integration, lifecycle management and value dashboards. Expanded at Knowledge 2026 into five dimensions: **Discover** (30+ integrations into AWS, Azure, Google Cloud, SAP, Oracle, Workday; non-human identities), **Observe** (runtime monitoring of agent reasoning, via the Traceloop acquisition), **Govern** (AI risk assessment over models, data sets, prompts, classic ML; five risk frameworks aligned to NIST and the EU AI Act), **Secure** (identity governance via Veza; detects agents exceeding permissions and shuts them down in real time), **Measure** (cost tracking and ROI dashboards against runaway model spend). GA of the enhancements August 2026; analysts report it is now included in all tiers. | [S1] [S2] [S3] *(3rd party for tiers)* |
| **Workflow Data Fabric, RaptorDB, Workflow Data Network** | A data layer connecting structured and unstructured data from external systems, with "zero-copy" connectors. RaptorDB Pro is ServiceNow's own database, claimed many times faster than the previous one. Workflow Data Network adds 100+ data partners (Snowflake, Databricks, SAP, Workday, Jira…) and the acquisition of a data-catalogue company. | [S7] [S7b] *(3rd party)* |
| **Workflow Studio, Integration Hub, spokes** | One builder combining Flow Designer, Playbooks, Decision Builder and Integration Hub. Playbooks suit processes with several human interactions (stage-based view); flows suit unattended automation. Spokes are packaged connectors (ITSM, RPA, Customer Service, …). | [S8] [S8b] |
| **Process Mining** | Mines event data from platform tables: automated discovery, variants and deviants, bottleneck analysis of activity transitions, ML clustering of variants, analyst workbench, cross-project comparison, a closed loop into an "Automation Center". | [S9] [S9b] |
| **CMDB / Service Graph** | Configuration items and their relationships to business services, filled by Service Graph Connectors from third-party discovery tools; basis for service mapping and downstream impact analysis. | [S10] *(3rd party)* |
| **Now Assist, Now Assist Guardian** | Generative-AI features across products. Guardian filters offensiveness, prompt injection and sensitive topics; blocked requests are not charged. Pricing reported as per-fulfiller add-ons plus consumption "assist packs". | [S11] [S12] *(3rd party pricing)* |
| **Service Catalog, Employee Center, AI front door** | Self-service catalogue of requestable services, surfaced in Employee Center, portal, mobile and virtual agent; AI search across catalogue and knowledge. Moveworks (enterprise search, front-end assistant) acquired, closed Dec 2025, about USD 2.4 bn. | [S13] [S14] [S19] |
| **Knowledge 2026 "Autonomous Workforce"** | Packaged "AI specialists" per function (IT, HR, finance, legal, security, CRM). Project Arc with NVIDIA: a desktop agent whose actions are logged, policy-bound and reversible. | [S3] [S17] *(3rd party)* |
| **Sovereignty** | Runs on hyperscaler regions; a German "Sovereign ServiceNow" is offered through T-Systems' cloud. | [S15] |

**Read for Taktus.** ServiceNow's 2026 thesis is explicitly the one Taktus holds: whoever governs
AI and runs workflows owns the enterprise operating layer [S3]. Its route is the opposite: one
proprietary platform, its own database, its own data network, enterprise tiers, everything else
pulled in. The ideas worth taking are the *governance and visibility shapes*, not the platform.

---

## 2. Ideas evaluated

### 2.1 Dropped, one line each

| ServiceNow idea | Why not in Taktus |
|---|---|
| Workflow Data Fabric / zero-copy / RaptorDB / Data Network | A data platform and system of record (P1, non-goal "not a tool landscape"). Taktus already references and never copies (ledger, provenance); a warehouse is a connector (UC-5.6). |
| Visual Flow Designer as main builder | Non-goal "not a visual block builder as the primary interface"; UC-12.3 says composed in dialogue. |
| LLM "dynamic orchestrator" choosing agents at runtime | Breaks UC-4.2 (the diagram is what runs) and method selection (P8): Taktus plans once, registers a version, and runs it. Planning stays Taktus's, at registration, not per run. |
| Observe = recording agent reasoning traces centrally | Ledger is content-free by construction. Traces belong in an optional observability backend (UC-5.8), not in Taktus's core. |
| Discover = scanning hyperscalers and SaaS for "shadow AI" | Enterprise-only, and inventory of other people's systems leans toward surveillance of what staff use (P14). A connector may *declare* AI it hosts; Taktus does not hunt for it. |
| Otto "workforce readiness" / staffing analysis | Assessment of people. Principle 14, unbuildable. |
| Packaged "AI specialists" per function | Already Taktus's blueprints (UC-15.1); ServiceNow's are bound to its tables, Taktus's to capabilities. Nothing new to take. |
| Per-fulfiller pricing, assist packs | Punishes success at level 4; the Takt exists for this (`docs/architecture/accounting.md`). |
| Integration Hub spokes as a proprietary catalogue | Taktus's connectors are capability-named and MCP-bound (UC-8.8); the lesson is breadth, met by the open MCP ecosystem, not a store. |
| Supervised vs. autonomous mode per tool | Validates, but Taktus already has more: levels 1–3 per process and per tool action, anchors independent of level (ADR-0039, ADR-0042). Usable as a sales comparison only. |
| Now Assist Guardian as a product | Fits only as a *check*, see 2.2.6. |

### 2.2 Fitting ideas

Effort: **S** about one pull request series inside one component; **M** a new read model or view
over existing records plus a use case; **L** a new capability with new data.

---

#### 2.2.1 The register of everything that acts — Taktus's "control tower"  ★ strongest

**At ServiceNow.** AI Control Tower: one inventory of every agent, model and workflow with
policy, risk, runtime state, cost and ROI, plus a real-time shutdown [S1] [S2].

**In Taktus.** A *read model*, not a new store: a view in the `reporting` component over the
catalogue entries (UC-8.6 models, UC-8.7 agents, UC-14.3 skills, UC-8.8 connectors), the
configured workers (ADR-0078), and the ledger. One row per **actor** — adapter (worker,
connector, model), agent, trained model, skill — showing:

- capability it serves; owner role; circle it is shared with;
- **autonomy**: highest level any process lets it act at, per tool action (ADR-0039), and the
  anchors that sit downstream of it;
- **exactness**: the strongest class of result it produces (`exact` means a check must stand behind it);
- **maturity**: conformance half and removal half; last `removal.tested` verdict (*broke /
  changed / untested / exception*) with the configuration it was taken under (ADR-0030);
- **residency**: where it processes data (UC-11.1), flagged where it contradicts the tenant's residency;
- **cost**: Takt consumption and money, period and trend (ADR-0010); spend against budget (ADR-0005);
- **evidence**: last evaluation, quality history behind its level, open incidents (UC-6.8);
- **stop**: the per-process emergency stop of every process that uses it (UC-7.2), one action.

What it adds that no current use case states: **one cross-cutting list**. Today each hub lists
its own kind, the bus-factor index counts, and the removal test reports per integration. Nothing
answers "what in this tenant can act, how far, at what cost, and is it proven replaceable?" in
one place. That is also the core of an **EU AI Act inventory for deployers**, generated from
configuration rather than written (P11 forbids a compliance claim not generated from the real
configuration).

- **Extends:** UC-8.6, UC-8.7, UC-14.3, UC-6.7, UC-8.9, UC-7.2, UC-11.1, UC-9.3. **Gap:** a new
  use case "the register of what acts", component `reporting` (ADR-0029: views are a component).
- **Serves:** P3, P7, P10, P11, P12, P13; P9 because every row with a problem carries its proposal.
- **Guardrails:** no column names a person, usage per person only to that person
  (`test_no_figure_names_a_person.py` already holds the line); a figure here is the same figure as
  in the cockpit, one definition (ADR-0029, P7); exportable as a file (P13); a stop is a person's act;
  an automatic stop stays a rule (ADR-0023).
- **Value across the spectrum:** a family sees "the four things that act for us, what each cost
  this month, which one could be swapped". A company gets its AI inventory and its vendor-exit
  proof. An operator hosting many tenants sees the same register per tenant and an aggregate per
  adapter across tenants (counts only), which tells them which adapter failing would hurt most.
- **Effort:** M (records exist; the read model and the view are new; AI Act mapping S on top).
- **Risks:** becoming the dashboard nobody reads (P9) — mitigate by default-sorting on "needs
  action" and hiding healthy rows; temptation to add "Discover" scanning (dropped above);
  AI Act wording is legal text — mark as not legally reviewed, as the anchor catalogue is (DEC-0029).

---

#### 2.2.2 The dependency graph and blast radius — Taktus's "service graph"  ★ strongest

**At ServiceNow.** CMDB plus Service Graph: what business service depends on which configuration
items, kept current by connectors, used for impact analysis [S10].

**In Taktus.** Not a CMDB (P1: the organisation's CMDB, if any, stays and can be read through a
connector). A graph **derived** from what Taktus already holds, never edited by hand:

```
process ──has──▶ step ──requires──▶ capability ──served by──▶ adapter ──reaches──▶ external system / provider (+ region)
   ▲                                                                       
   └──reads result of── step of another process   (from provenance, ADR-0021)
step ──halts at──▶ anchor (legal / strategic / correction)
```

Questions it answers, each in one click:

1. **"If this goes away"** — select a provider, adapter or model version: every process and step
   that loses it, split into *breaks* (only adapter), *degrades* (alternative or person exists),
   with the last removal verdict as evidence. This is the removal test made interactive.
2. **"If this was wrong"** — select a result or step: the forward provenance chain, which steps
   in other processes read it, their exactness class, whether anything left the system
   (`egress.*`) and which correction anchor would fire. This is UC-4.11 drawn.
3. **"Where is our data"** — colour by region; edges that cross the tenant's residency stand out.

- **Extends:** UC-6.7 (which already promises "the graph of dependencies" but specifies no view),
  UC-8.9, UC-4.11, UC-15.4 (end-to-end chains), UC-11.1. **Gap:** the view and the query; the
  provenance half needs `ProvenanceQuery.chain` read forward across processes.
- **Serves:** P6, P11, P12, P13.
- **Guardrails:** derived only (one source, like the diagram of UC-4.2); people appear as roles on
  `human` steps, never by name; a "what if" is analysis and never anchored, acting on it is.
- **Value:** the household sees "if the bank connector stops, these two reminders stop".
  A company does change and incident impact without maintaining a CMDB. An operator sees which
  shared adapter or provider outage hits how many tenants and processes — a direct input to its
  own operations and contracts.
- **Effort:** M for the structural graph (bundles + configuration), M more for the provenance
  overlay (data exists since ADR-0021; forward walk and graph layout are new).
- **Risks:** graphs of real tenants get unreadable — start from a selected node, never draw the
  whole; drift between graph and runtime is impossible only if both read the registered
  version and live configuration, never a copy.

---

#### 2.2.3 Process mining over Taktus's own ledger — variants and conformance  ★ strongest

**At ServiceNow.** Process Mining discovers variants and deviants from event tables, finds slow
transitions, clusters variants and feeds improvements into an automation backlog [S9] [S9b].

**In Taktus.** Taktus has the event log already: hash-chained, content-free step entries with
method, adapter, outcome token and consumption per run (control-plane §6). The designed graph is
the process version. Mining compares **the designed path with the travelled paths**:

- **variants per process version** — sequence of step outcomes including retries, fallbacks
  taken (`llm → human`), anchor halts, rehearsal vs. real, and the share of runs per variant;
- **conformance** — share of runs on the happy path; where runs leave it, which step and which cause;
- **time overlay** — per edge: working time vs. blocked time with the seven causes of UC-9.5
  (provider limit, quota, budget, compute, a person, external state, other work);
- **proposals** — a frequent fallback to `human` is a candidate for a better method or a rule
  (ADR-0084 maturation); a frequent wait on one role is a limit-health or staffing-of-roles
  proposal (UC-4.4), never a statement about a person.

Second stage, matching UC-9.4: mining **external** event logs read through a connector (a ticket
tool's state history), to find processes nobody wrote down, and to see how a **decoupled**
process (P5) really runs outside Taktus.

- **Extends:** UC-9.5 (bottlenecks, building), UC-9.1 (cockpit figures), UC-4.4 (proposals),
  UC-6.10 process level, UC-9.4 (external discovery). **Gap:** variant and conformance analysis
  over the ledger is in no use case. Check before building: whether "fallback taken" and
  "retry" are distinct ledger facts today; if not, that is a new fact kind (and a finding).
- **Serves:** P8, P9, P10 (quality history for a raise), P14 *permits and asks for* this analysis
  "per process, step, role and department".
- **Guardrails:** case-level, never person-level; aggregation by role with the two-person floor
  already applied to response times (ADR-0042); external logs are read content-free (identifiers,
  state, time), and a column naming the agent of a ticket is dropped at the connector, not hidden in the view.
- **Value:** a family hardly needs variants — show only "this reminder needed you 3 times this
  month". A company gets process mining without a separate tool for everything Taktus runs. An
  operator compares variant rates of the same blueprint across tenants (counts only, opt-in —
  aligns with the post-1.0 "anonymous value benchmarks").
- **Effort:** M for ledger mining (data exists), L for external-log mining (connector capability,
  mapping, privacy filtering).
- **Risks:** in Taktus variant space is small by design, so the value lies in fallback, wait and
  anchor rates rather than spaghetti maps — do not import ServiceNow's heavy workbench; external
  mining is where surveillance creeps in.

---

#### 2.2.4 An outcome catalogue — what a person can ask Taktus for

**At ServiceNow.** Service Catalog and Employee Center: requestable items, a portal, request
tracking, AI search; Moveworks as conversational front door [S13] [S14].

**In Taktus.** A view of the **registered process versions a person may start**, by circle, in
plain language: what you get, what it needs from you, typical duration and cost (from the
admission estimate and history, ADR-0005), its autonomy statement, and which acts stay with a
person. Starting one is an ordinary command (UC-1.1) — from the web app, chat or any channel —
and tracking is the run view, not a ticket. "Nothing here fits" turns into the dialogue that
proposes a new process (UC-1.2, UC-4.1).

- **Extends:** UC-1.1, UC-6.4 (employee view: "what waits for me"), UC-10.3, UC-12.3, UC-15.1.
  **Gap:** no use case lists startable processes to a non-technical person.
- **Serves:** P4, P10, P14 (people start outcomes, not tickets), P1 only if guarded.
- **Guardrails (P1):** no request object of its own; where the organisation has a ticket or
  request system, the request is mirrored there (UC-5.3); the catalogue is a projection of
  registered versions and is switchable off.
- **Value:** family: a small "what Taktus can do for us" menu; company: self-service without IT
  tickets; operator: the natural start page for its B2C/B2B customers, with its own branding.
- **Effort:** M. **Risks:** the highest P1 risk of all ideas — the step from catalogue to ITSM
  portal is small. Keep it a list plus a start button.

---

#### 2.2.5 Stage view for people inside a run (from Playbooks)

**At ServiceNow.** Playbooks show a process as stages for processes with several human
interactions [S8]. **In Taktus.** For a person who takes part in a run (approver, `human` step),
a stage-strip of the run grouped by the steps that involve them: done, theirs now, after them.
Extends UC-6.10 (run level) and UC-6.4. Serves P7, P14. Effort **S** (records and live stream
exist, ADR-0055). Risk: a second diagram — must derive from the version, like UC-4.2.

#### 2.2.6 Input guards as a check, not a product (from Now Assist Guardian)

**At ServiceNow.** Guardian detects prompt injection, offensive content, sensitive topics [S11].
**In Taktus.** A `guard` capability as an `ml`/`rule` step or a model-adapter wrapper, applied to
content from outside (channels, contributions of unknown people, UC-1.9) before an `llm` or
`worker` step reads it; a hit records a token in the ledger and routes to `human`. Extends
UC-1.9, UC-8.4. Serves P8, P12. Effort **S–M**. Risk: false confidence — state it in the
exactness statement as a check with named gaps, never as "safe".

#### 2.2.7 Agent interoperability through A2A (from AI Agent Fabric)

**At ServiceNow.** MCP and A2A connect native and third-party agents [S16]. **In Taktus.** MCP is
already the connector binding. An **A2A binding of the worker contract** lets an external agent
be a worker (a capability served by an adapter) and lets Taktus expose a process as an agent to
other systems, with anchors and budgets applying unchanged. Extends UC-14.1, UC-8.7. Serves P3,
P4, P13. Effort **M**. Risk: protocol churn — keep it in an adapter (non-goal: no foreign runtime
in the core).

---

## 3. Screens for the three strongest ideas

### 3.1 "What acts for us" — the register

**Layout (desktop).** Header: tenant name, period selector, two counters — *needs attention* and
*all actors*. Left rail: filters by kind (worker, connector, model, agent, skill), by circle, and
toggles *needs attention only* (default on), *above level 2*, *produces exact results*,
*outside residency*.

**Main table**, one row per actor:

| Kind | Capability (name) | Owner role | Level ▲ | Exactness | Removal | Residency | Cost (Takt · €, trend) | Last eval | ⏻ |
|---|---|---|---|---|---|---|---|---|---|

- *Level* shows the highest level and a small marker if any anchor sits downstream.
- *Removal* is a chip: green *changed*, amber *untested*, red *broke*, grey *exception* — with the
  date and "taken under config X".
- *Cost* is a sparkline over the period; budget share as a thin bar.
- Rows that need action are first and carry a one-line reason ("removal broke in 2 processes",
  "region differs from tenant residency", "level 3 without quality history since version 7").

**Interactions.** Click a row → right drawer: plain-language description (what it does, reads,
must not do — UC-8.7), processes using it with their level per tool action, evidence (evaluations,
removal runs, incidents), and the proposal Taktus raised, with *accept → decision request*.
*⏻* opens the emergency stop for the processes using it — names them, asks for confirmation,
records the act. *Export* (CSV/JSON) and *AI Act inventory* (generated, marked "not legally
reviewed") at the top right. Mobile: cards, attention first, drawer as a full page.

### 3.2 "If this goes away" — the dependency graph

**Layout.** Search box at the top ("provider, adapter, model, process, result…"). Below, a
three-column layered graph, left to right: **processes → capabilities → adapters / providers**,
with region badges on providers. A segmented control switches mode: *Remove*, *Wrong result*,
*Residency*.

- **Remove mode.** Select a node (e.g. a model provider). Everything downstream of it lights up:
  red edges where it is the only adapter (*breaks*), amber where an alternative or a person exists
  (*degrades*). A side panel lists the affected processes with their step, the alternative,
  the last removal verdict and its date, and how many runs per week pass through.
- **Wrong result mode.** Select a step or a result. The graph turns into a left-to-right
  provenance flow: the result, the steps in this and other processes that read it, each with
  its exactness badge; nodes that sent data out carry an *egress* marker; a correction-anchor
  icon marks where a person must decide. A footer gives the four counts of UC-4.11 (since when,
  affected, built on it, left the system).
- **Residency mode.** Providers coloured by region; edges crossing the tenant's residency drawn bold.

**Interactions.** Click to expand one level at a time (never the whole tenant at once); breadcrumb
to go back; "open removal run" and "open run" links; *export graph* as JSON and as an image.

### 3.3 "How it really runs" — variants and waiting of one process

**Layout.** Header: process name, version selector, period, autonomy statement, run count.
Top band: four tiles — *on designed path* %, *fallback to a person* %, *anchor halts* per week,
*blocked share of lead time* %.

**Centre.** The process diagram of the selected version (UC-4.2), with edge thickness = share of
runs and node colour = blocked time; each node shows working vs. waiting time as a split bar
coloured by cause (seven causes of UC-9.5). Steps drawn by method kind as in UC-6.10.

**Right panel: variants.** A ranked list: "1 · designed path · 71 %", "2 · fallback at
*classify* → person · 18 %", "3 · retry at *fetch invoice* · 7 %", … Selecting a variant highlights
its path on the diagram and lists sample run links.

**Bottom: proposals.** Cards generated from the figures, each with evidence and an action:
"*classify* fell back to a person in 18 % of runs; a classifier trained on 640 labelled cases
would agree in 96 % — propose method change" → decision request. "Waits on role *accounts
approver* make up 40 % of lead time; consider a threshold below which approval is a rule" →
decision request.

**Rules visible in the UI.** No person filter exists. Role figures show only where at least two
people hold the role in the period; otherwise "too few to show". A person opening the page sees
their own share of waiting in a separate, private box.

---

## Sources (accessed 2026-10-12)

- [S0] https://www.servicenow.com/de/platform.html — HTTP 403 to automated access
- [S1] https://newsroom.servicenow.com/press-releases/details/2025/ServiceNow-Launches-AI-Control-Tower-a-Centralized-Command-Center-to-Govern-Manage-Secure-and-Realize-Value-From-Any-AI-Agent-Model-and-Workflow/default.aspx
- [S2] https://newsroom.servicenow.com/press-releases/details/2026/ServiceNow-expands-AI-Control-Tower-to-discover-observe-govern-secure-and-measure-AI-deployed-across-any-system-in-the-enterprise/default.aspx
- [S3] https://nand-research.com/servicenow-knowledge-2026-the-agentic-enterprise-takes-shape/ (3rd party)
- [S4] https://www.constellationr.com/blog-news/insights/servicenow-launches-ai-orchestrator-partners-google-cloud-oracle-reports-q4 (3rd party)
- [S5] https://www.servicenow.com/docs/r/zurich/intelligent-experiences/understand-na-aia.html
- [S6] https://www.servicenow.com/docs/r/build-workflows/workflow-studio/use-an-ai-agent-action.html
- [S7] https://www.constellationr.com/insights/news/servicenow-launches-workflow-data-network-acquires-dataworld (3rd party)
- [S7b] https://www.servicenow.com/customers/now-on-now-raptordb.html
- [S8] https://www.servicenow.com/docs/r/0MvJg~UYByX0VxWLomI71w/NGZ0dmt8XAMqKdvorZDlEQ (Exploring Workflow Studio)
- [S8b] https://www.servicenow.com/docs/r/build-workflows/workflow-studio/spokes.html
- [S9] https://www.servicenow.com/docs/r/3dUp4IlSpaXzwDcoDj_v6g/c16qvl_WnT83lSx5xQGIUQ (Key features of Process Mining)
- [S9b] https://www.servicenow.com/products/process-optimization.html
- [S10] https://www.suretysystems.com/insights/servicenow-service-graph-connectors-guide-surety-systems/ (3rd party)
- [S11] https://www.servicenow.com/community/servicenow-otto-articles/now-assist-guardian-faq/ta-p/3065004
- [S12] https://redresscompliance.com/servicenow-now-assist-ai-licensing.html (3rd party)
- [S13] https://www.servicenow.com/docs/r/servicenow-platform/service-catalog/service-catalog.html
- [S14] https://www.businesswire.com/news/home/20251215128980/en/ServiceNow-completes-acquisition-of-Moveworks
- [S15] https://www.t-systems.com/de/en/digital/gated-content/digital-sovereignty-with-servicenow
- [S16] https://thenewstack.io/servicenow-launches-a-control-tower-for-agents/ (3rd party)
- [S17] https://itdaily.com/news/software/servicenow-rolls-out-ai-specialists-for-it-crm-hr-and-security/ (3rd party)
- [S18] https://www.cio.com/article/3813359/servicenow-adds-ai-agent-orchestrator-studio-to-its-now-platform.html (3rd party)
- [S19] https://www.sec.gov/Archives/edgar/data/0001373715/000137371526000076/now-20260630.htm (10-Q, Moveworks price)

Taktus sources read: `CLAUDE.md`, `docs/vision/principles.md`, `non-goals.md`, `market.md`,
`docs/architecture/governance.md`, `methods.md`, `control-plane.md` §4–6, `accounting.md`,
`docs/roadmap.md`, `docs/adr/README.md`, and use cases UC-1.1, 4.1, 4.2, 4.11, 6.4, 6.7, 6.10,
8.6, 8.7, 8.9, 9.1, 9.4, 9.5, 10.3, 12.3, 13.6, 14.3, 15.1.

---

# Part 3 — LiteLLM and OmniRoute


Product-owner analysis, 2026-10-12. Facts from the projects' repositories, docs and the GitHub
API on that date; Taktus facts from the repository at `6aa82a7`. Summaries, not quotations.

---

## 1. What each project is

### 1.1 LiteLLM (BerriAI)

**What it is.** A Python SDK and a self-hosted proxy ("AI gateway") that puts one
OpenAI-compatible endpoint in front of 100+ providers. The proxy adds virtual keys, budgets and
rate limits, spend tracking, routing with fallbacks, response caching, guardrails, an MCP
gateway, an A2A agent gateway and logging callbacks.
<https://github.com/BerriAI/litellm> · <https://docs.litellm.ai>

| Fact | Value (2026-10-12) |
|---|---|
| Owner | BerriAI Inc. (organisation, US start-up) |
| Licence | **Split.** MIT for everything outside `enterprise/`; `enterprise/` is under a proprietary BerriAI Enterprise licence that permits production use only with a paid subscription and seat count (`LICENSE`, `enterprise/LICENSE.md` in the repo). GitHub shows `NOASSERTION`. |
| Activity | Created 2023-07; last push 2026-10-12; releases v1.104.3, v1.105.0 and v1.106.0-rc.1 all on 2026-10-11. ~54k commits; top contributors are company staff. |
| Popularity | 61.1k stars, 12.3k forks, ~5,460 open issues and PRs. |
| Data model | Postgres required for virtual keys, budgets and spend; Redis required for shared state across several proxy instances (cooldowns, TPM/RPM, cache). <https://docs.litellm.ai/docs/proxy/virtual_keys>, <https://docs.litellm.ai/docs/routing> |

**Features relevant to Taktus (from the docs):**

- **Virtual keys** with allowed models, aliases, metadata, team/user owner, `max_budget`,
  expiry, `tpm_limit`/`rpm_limit`; spend per key, user, team.
  <https://docs.litellm.ai/docs/proxy/virtual_keys>
- **Budgets and rate limits** at proxy, organisation/team, team member, user, key, end-customer
  and per model; `budget_duration` resets; a budget reservation of the estimated maximum cost
  before a request; budgets are **unenforced without a database (fail open)** unless
  `fail_closed_budget_enforcement` is set; a crossed budget is an error response, not a wait.
  Per-model budgets on keys/users are enterprise-only.
  <https://docs.litellm.ai/docs/proxy/users>
- **Cost tracking** from `model_prices_and_context_window.json`, custom prices per deployment,
  margins for resale, a `x-litellm-response-cost` header, spend logs and reports per
  team/key/customer. Tag-based allocation and billing reports are enterprise-only.
  <https://docs.litellm.ai/docs/proxy/cost_tracking>
- **The price map.** One JSON file, 2.6 MB, **4,042 entries** today, inside the MIT part. Per
  model: `input_cost_per_token`, `output_cost_per_token` (~3,260 entries),
  `cache_read_input_token_cost` (1,402), `cache_creation_input_token_cost` (442), context
  limits, `litellm_provider`, `mode`, `supports_*` flags, `deprecation_date`, `source`, and
  variant prices (batch, flex, priority; 416 entries with tiered "above N tokens" prices).
  <https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json>
- **Routing**: simple-shuffle (default, by rpm/tpm weights), least-busy, usage-based, latency-based,
  cost-based; fallbacks on context window, content policy and generic errors; cooldown of a
  deployment after `allowed_fails`; exponential backoff on rate-limit errors.
  <https://docs.litellm.ai/docs/routing>
- **Caching**: exact-match (in-memory, Redis, S3, GCS, disk) and semantic (Redis, Qdrant).
  The docs do not say what usage a cache hit reports. <https://docs.litellm.ai/docs/proxy/caching>
- **Prompt-cache usage**: `prompt_tokens` includes cached and cache-written tokens;
  `prompt_tokens_details.cached_tokens` for reads; cache *writes* are reported per provider —
  e.g. a top-level `cache_creation_input_tokens` for one vendor, `cache_write_tokens` for
  another. <https://docs.litellm.ai/docs/completion/prompt_caching>
- **Guardrails**: pre-call, during-call, post-call, logging-only; integrations for PII masking,
  content safety and custom APIs. Per-key/team guardrails are enterprise-only.
  <https://docs.litellm.ai/docs/proxy/guardrails/quick_start>
- **MCP gateway**: one endpoint over many MCP servers with per-key/team access, OAuth and
  passthrough auth, stdio/SSE/streamable HTTP. <https://docs.litellm.ai/docs/mcp>
- **A2A gateway**: register and invoke agents, spend attributed per agent via headers.
  <https://docs.litellm.ai/docs/a2a>
- **Logging callbacks**: OpenTelemetry, Langfuse, Datadog, S3 and many others; some sinks and
  per-request callback control are enterprise-only. <https://docs.litellm.ai/docs/proxy/logging>
- **Enterprise-only** (paid, price on request): SSO/SCIM, audit logs, RBAC, IP allow-lists, key
  rotation, secret-manager integration, "multi-tenant architecture" (organisations, projects),
  tag budgets, team-based logging, per-key guardrails. <https://docs.litellm.ai/docs/enterprise>

**Security and supply chain — verified.**

- **PyPI compromise, 2026-03-24.** `litellm` 1.82.7 and 1.82.8 were published with a
  credential-stealing payload (SSH keys, cloud credentials, Kubernetes secrets); 1.82.8 shipped a
  `.pth` file that runs on **every Python start** in the environment. Root cause per the vendor:
  a compromised CI dependency (a security scanner) let the attacker upload directly to PyPI. The
  official proxy Docker image (`ghcr.io/berriai/litellm`) was not affected because it pins its
  dependencies. Response: a new CI/CD pipeline, cosign-signed images, a list of verified
  checksums, clean v1.83.0.
  <https://docs.litellm.ai/blog/security-update-march-2026> ·
  <https://www.netspi.com/blog/executive-blog/ai-ml-pentesting/litellm-supply-chain-compromise/> ·
  <https://futuresearch.ai/blog/litellm-pypi-supply-chain-attack/>
- **Advisories on the proxy, 2026 alone (GitHub security advisories): 17**, of them **4 critical**
  (OIDC cache-key auth bypass 04-03, SQL injection in key verification 04-20, host-header auth
  bypass 05-28, privilege escalation to proxy admin via salt-key reuse 09-30) and **6 high**
  (pass-the-hash, config-endpoint privilege escalation, template injection, command execution via
  MCP stdio test endpoints, MCP OAuth bypass, local file read 10-01).
  <https://github.com/BerriAI/litellm/security/advisories>

**Reading.** Mature, very active, the de-facto open gateway. But: a large attack surface that is
patched often (roughly one critical a quarter), a release cadence of several versions a day, the
governance features an operator of many tenants needs are behind a proprietary licence, and the
Python package was a credential stealer for 40+ minutes this year.

### 1.2 OmniRoute (diegosouzapw)

**What it is.** A TypeScript/Node gateway, local-first (desktop app, PWA, Docker, edge
runtimes), aimed at **coding-agent users** (Claude Code, Codex, Cursor, Cline, …) who want to
"never stop coding": one endpoint at `localhost:20128/v1` that cascades across a subscription,
then API keys, then cheap, then **free-tier** providers. Claims 372 providers, 154 with free
tiers, 19 routing strategies, a 12-engine **prompt compression** stack (15–95 % fewer tokens),
semantic caching, an MCP server with 110 tools, A2A, per-key USD caps, SQLite persistence.
Started as a fork of 9router plus a port of CLIProxyAPI.
<https://github.com/diegosouzapw/OmniRoute> ·
<https://instagit.com/diegosouzapw/OmniRoute/history-of-omni-route/>

| Fact | Value (2026-10-12) |
|---|---|
| Owner | one individual (user account, not an organisation); 5,260 of the commits are his, next contributor 306 |
| Licence | MIT |
| Activity | Created **2026-02-13**; last push 2026-10-11; releases v3.8.50 (08-26), v3.8.51 (09-30); ~10k commits |
| Popularity | 75.6k stars, 10.9k forks — up from ~34k stars in July 2026 per a third-party write-up, i.e. +40k in three months for an eight-month-old single-owner repo. **Treat the star count as unreliable.** <https://agentpedia.codes/blog/omniroute-ai-gateway-routing-setup-guide.md> |
| Funding | sponsorship by a model vendor; partner/affiliate links (`aff=omniroute`) |

**Security posture — red flags.**

- **Consumer-subscription reuse.** It accepts OAuth sessions of coding-tool *subscriptions* and
  serves API traffic through them; it advertises **TLS fingerprint "stealth" to evade detection**
  and a **MITM/TPROXY mode** with its own CA to capture CLI tools that ignore proxy settings.
  That is designed to look like the vendor's own client — a likely breach of provider terms and
  a risk of account suspension for the customer. <https://pinggy.io/blog/omniroute_ai_gateway_security/>
- **Defaults.** Dashboard password defaults to a literal placeholder until set; MCP tool scope
  enforcement is opt-in. (same source)
- **Advisory:** critical **remote code execution** via custom ACP agents, 2026-09-03.
  <https://github.com/diegosouzapw/OmniRoute/security/advisories/GHSA-hf57-cqmx-p4gr>
- A critical third-party review titled, in essence, "why you shouldn't touch it".
  <https://levelup.gitconnected.com/the-ai-tool-that-promises-1-6-billion-free-claude-tokens-and-why-you-shouldnt-touch-it-a63c687f7d91>

**Reading.** A hobbyist/prosumer cost-evasion tool, not infrastructure. Bus factor of one, an
inflated popularity signal, and a core value proposition (free tiers, subscription reuse, stealth,
silent prompt compression) that collides head-on with sovereignty, provenance and exactness.

---

## 2. Options for Taktus

### 2.1 Taktus as it stands (what the options are measured against)

- One model adapter, chat-completions dialect, `POST {endpoint}/chat/completions`, bearer
  credential (`src/taktus/adapters/driven/models/openai_compatible/client.py`).
- One configured model per instance: `TAKTUS_MODEL_ENDPOINT`, `TAKTUS_MODEL_NAME`,
  `TAKTUS_MODEL_PURPOSES` (`src/taktus/composition/settings.py`); `StaticModelPool` takes the
  first member that serves a purpose — no chain, no policy (`models/pool.py`).
- Admission reserves an upper-bound input count (1 token/byte + 16 per message + 16 per request)
  plus the output limit, priced at the configured model's price in the versioned `PriceTable`
  (`execute_run.py` ~L1860; `contracts/model/v1/README.md` §3, §6; ADR-0005).
- Usage recorded per model **as the endpoint names it** (`completion.model`) and per price kind
  (`Consumption.tokens_by_model`); money recomputed by `taktusctl cost` (ADR-0010).
- 429 → `ModelAtLimit` → step back to its boundary, run halts with cause `capacity`, runner
  defers with doubling delay up to a minute, wait booked to `limit.provider` (ADR-0043).
- Specified but not built: routing per task with policy, reproducible and in provenance
  (**UC-8.2**, 0.4.0); budgets per unit with inheritance and a "continue on a cheaper model"
  policy (**UC-8.5**, building); residency per tenant/process/data class with declared adapter
  locations (**UC-11.1**). Non-goals: *no foreign gateway as the core; libraries may be used
  inside an adapter* (`docs/vision/non-goals.md`).

### 2.2 Option (a) — a gateway as an optional deployment component behind the existing adapter

The operator points `TAKTUS_MODEL_ENDPOINT` at the gateway and puts a gateway key in the model
credential file. **No code change is needed for it to run.** What holds and what does not,
checked against `openai_compatible/client.py` and `execute_run.py`:

| Concern | Through LiteLLM | Verdict |
|---|---|---|
| Dialect, auth | `/chat/completions`, bearer virtual key | **works** |
| Input count (M-02) | upper bound unaffected — *unless* the gateway adds text (injected system prompts, guardrail templates, cache-control injection) | works for a pass-through; M-02 catches the rest |
| Output cap (M-03) | `max_tokens` forwarded | same as the provider behind it |
| Input / output tokens | `prompt_tokens`, `completion_tokens` | **works** |
| Cache read | `prompt_tokens_details.cached_tokens` | **works** |
| Cache write | LiteLLM reports one vendor's writes as top-level `usage.cache_creation_input_tokens`; the adapter reads only `prompt_tokens_details.cache_write_tokens` | **gap:** writes are booked as uncached input — money **under-stated** (writes are dearer). The declaration names only `input, output`, so M-04 does not catch it. |
| Model identity | Estimate is reserved under the configured name (`resolved.version`); actuals are booked under the name the gateway returns | **gap** when the gateway answers with an alias's underlying name or a fallback: the price table must hold both names, and a fallback to a dearer model breaks the currency reservation. Provenance names whatever the gateway reports. |
| Gateway fallbacks / load balancing | invisible to Taktus | **conflicts with UC-8.2**: a route not reproducible and not in the ledger |
| Response cache | usage on a hit undocumented | **unknown**: Taktus may book tokens never billed, or none |
| 429 from the gateway's own key limit | → `ModelAtLimit`, wait | works, but booked to `limit.provider` though the limit is the operator's own; `Retry-After` is not read |
| 429 from the provider | LiteLLM retries with backoff internally first | works; the retry time is hidden inside the step, not booked as blocked time |
| Gateway budget crossed | error response (4xx `ExceededBudget`) | **gap:** → `ModelError` → step *fails* "model unavailable". A second budget authority producing failures instead of admission refusals. |
| Model listing (`/v1/models`) | available | **unused**: Taktus lists nothing; the pool is static. No gain. |
| Residency (UC-11.1) | one alias may fan out to several providers and regions | the adapter's declared location must be the **widest** behind the alias, or residency is unprovable |
| Removal test | gateway removed = endpoint pointed at the provider | passes **only** for a 1:1 pass-through |
| Conformance M-01..M-04 | `taktusctl conformance run --endpoint <gateway>` | **works**; run it per alias |

**Verdict (a), LiteLLM:** acceptable as an **operator's optional component in a
"pass-through profile"**: one alias → one deployment, no fallbacks or load balancing, no response
cache, no prompt rewriting, gateway budgets off or set as an outer backstop above Taktus's
budget plus margin, the proxy run from the signed Docker image (not the PyPI package), its
location declared as the widest provider behind it. In that profile it adds key isolation and a
second observability trail; it adds nothing Taktus's accounting needs. Three small adapter fixes
would make any gateway — and several providers' own compatible endpoints — book correctly
(effort **S**): read `cache_creation_input_tokens`/`cache_read_input_tokens` beside
`prompt_tokens_details`; let the operator declare cache kinds so M-04 holds them; read
`Retry-After` into the deferral; map a gateway budget refusal to a named limit, not
"model unavailable".

**Verdict (a), OmniRoute: not supported.** Same dialect, but its defaults rewrite prompts
(compression — the recorded input is not what was sent, which breaks provenance and makes a
`sourced` step unreproducible), route dynamically (`auto`, 16-factor scoring), and reach models
through consumer subscriptions with detection evasion. Taktus should say so in its
documentation rather than stay silent.

### 2.3 Option (b) — adopt the concepts natively

Effort: S ≤ a pull request; M = a few pull requests, one ADR; L = an epic across components.

| # | Concept | Principle(s) | Component | Gap vs existing design | Effort |
|---|---|---|---|---|---|
| 1 | **Importable open price map → versioned `PriceTable`.** `taktusctl prices import <file> --source … --valid-from …` maps per-token prices to the four kinds (`input`, `output`, `cache_read`, `cache_write`) per `unit_tokens`, writes a new table version, never edits one in use. The map's schema is MIT-licensed data; the importer lives in an adapter/CLI, never names the product in the core. | 8, 11 (no black-box bill), 13 | accounting, CLI | Repository ships no prices on purpose (contract §6) — still true: the operator imports. Tiered, batch/flex/priority prices are not representable → named as unpriced, a later contract change. A diff against the current table is a "price drift" notice (ADR-0005 §5). | **S** |
| 2 | **Routing policy per purpose with an ordered fallback chain.** Purpose → ordered members; each member eligible by evaluation (UC-8.4), residency (UC-11.1) and exactness; choice deterministic from declared needs and member state; route and reason in provenance; fallback taken **at the step boundary** with a fresh estimate at the new member's price — never mid-call. Covers UC-8.5's "continue on a cheaper model". | 3, 8, 10, 13 | catalog (policy), run (admission), composition (multi-model config) | UC-8.2 is specified for 0.4.0; settings hold one model; `StaticModelPool` is first-match. | **M** |
| 3 | **Rate-limit-aware routing feeding admission and blocked time.** Each member declares its known limits (rpm, tpm, subscription window); admission counts against them like a budget; a 429 with `Retry-After` defers to that moment; a member at its limit is skipped for the next eligible one, and the wait or the switch is booked (`limit.provider`). A member that keeps failing is held out for a cooldown (ADR-0047's noticed-broken interface). | 8, 12 | run, throughput | 429 handled reactively; no proactive window accounting; `provider_limit` is monthly information only. | **M** |
| 4 | **Per-tenant credentials and per-unit budgets ("virtual keys", done Taktus's way).** A tenant binds its own model credentials (bring-your-own-key) or the operator's; budgets per unit (tenant → department → team → process) inherit and never admit what a parent refuses; per-tenant price table with an operator margin for resale. Attribution by tenant/role/department; **never a per-person ranking**. | 7, 12, 13, 14 | identity, accounting, run, secret store | Tenant boundary exists (ADR-0020); one model credential per instance; run budgets exist, unit hierarchy is UC-8.5 building. | **L** |
| 5 | **Provider prompt caching, booked correctly.** Ask for provider-side caching where the dialect allows; book reads/writes per kind (fix in 2.2). Big saving on repeated system prompts. | 8, 9 | model adapter | Parsing exists; nothing requests caching; write field gap. | **S–M** |
| 6 | **Exact-match response reuse** for steps whose exactness and method permit it: a reuse is a recorded source ("answer of run R step S"), not a hidden hit. | 8 | run, ledger | None today. Semantic caching excluded (see 2.4). | **M** |
| 7 | **Guardrails as visible steps.** PII masking / secret redaction as a `rule` or `ml` step before an `llm` step, declared in the process and checked by the residency rule — not a hook inside a proxy the ledger cannot see. | 8, 11, 14 | process bundles, workers | Log masking exists; no pre-call data-class step. | **M** |
| 8 | MCP tool gateway / A2A | 4, 13 | connector | Already covered by the connector contract's MCP binding (ADR-0024) and its frame; nothing to adopt now. | — |
| 9 | Logging callbacks | 8 | telemetry | Already OpenTelemetry from day one (control-plane §8). | — |

### 2.4 Option (c) — what not to adopt

- **A gateway's budget or spend as an authority.** Two truths: Taktus reserves before a step,
  the gateway refuses mid-run with a 4xx that becomes a failure; LiteLLM budgets fail open
  without their database. The ledger is the one truth for money (ADR-0005, ADR-0010).
- **Dynamic routing inside a gateway** (latency-, least-busy-, cost-based, fallbacks, `auto`).
  Not reproducible, not in provenance, residency unprovable — contradicts UC-8.2 and UC-11.1.
- **A gateway as a mandatory dependency.** ADR-0002: PostgreSQL is the only one. LiteLLM in
  multi-instance operation adds Postgres-for-the-gateway and Redis; that is the smallest
  installation's burden for no gain.
- **`litellm` as a Python library inside Taktus's process.** The March 2026 `.pth` payload ran
  on every interpreter start; Taktus's runner holds every credential of the instance. The
  non-goals permit libraries inside an adapter — this one should not be one. The adapter's
  ~200 lines of `httpx` are the better trade.
- **Enterprise-gated governance** (SSO, RBAC, organisations, per-key guardrails, tag budgets).
  An operator hosting many customers would need the paid licence — vendor lock-in through the
  back door (principle 13).
- **OmniRoute, entirely.** Terms-of-service evasion, MITM/stealth, a critical RCE, a bus factor
  of one, silent prompt rewriting.
- **Semantic caching and prompt compression.** Returns or sends something other than what the
  step asked for; violates provenance and exactness.
- **Per-user spend views** as both tools offer them. Principle 14: aggregate by role or
  department; a person sees only their own.
- **A live, unversioned price source.** Prices are imported into a version and never changed
  once used.

---

## 3. Recommendation

1. **Support a gateway, do not depend on one.** Document a *pass-through profile* for LiteLLM
   (1:1 alias, no fallbacks, no cache, signed image, location declared, budget as outer
   backstop only). State that OmniRoute is not supported and why. No core change.
2. **Fix the adapter now (S).** Cache-write field, declarable cache kinds for M-04, `Retry-After`,
   gateway budget refusal named as a limit. The cache-write gap under-states money wherever an
   endpoint reports writes at the top level — worth checking against the providers' own
   compatible endpoints too; if confirmed it is a result defect in recorded money.
3. **Price-map importer next (S).** Highest value per effort: the operator gets 4,000 prices
   with cache kinds into a versioned table in one command.
4. **Purpose routing with fallback chain and rate-limit awareness (M) for UC-8.2 / 0.4.0** —
   the native replacement for the gateway's router, reproducible and in the ledger.
5. **Per-tenant credentials and unit budgets (L)** with UC-8.5 and the identity component — the
   piece operators hosting many customers will ask for first.

Owner-facing classification (for whoever turns this into work): items 1–3 are ordinary
backlog work under existing ADRs; item 4 implements an existing use case (UC-8.2) and needs its
ADR before code; item 4 of §2.3 touches UC-8.5 and identity; none is a new requirement.

### 3.1 Screen: "Model routing" (per tenant)

**Purpose.** An operator or tenant administrator sees, per model purpose, which models serve it
in what order, why, what they cost, how close each is to a limit, and what Taktus did today.

**Header bar.** Tenant selector · price table in force (version, valid-from, "imported from …",
drift badge if a newer import differs) · weighting table (version, "uncalibrated") ·
residency rule of the tenant (e.g. "EU only; class *personal* → own infrastructure").

**Left column — purposes.** A list: `triage`, `reasoning`, `coding`, `embedding`, … Each row:
name, number of members, a status dot (green: first member serving; amber: running on a
fallback or a member at limit; red: no eligible member or a member unpriced under a currency
budget), steps routed in the last 24 h.

**Main panel — the chain of the selected purpose.** An ordered table, drag handle per row
(reordering creates a *draft* configuration change, applied on approval, never live):

| Column | Example |
|---|---|
| Order | 1, 2, 3 |
| Member (adapter id, never a product in the core view) | `eu-large`, `local-small`, `eu-medium` |
| Model @ pinned version | as the endpoint names it |
| Supply | api key · subscription · local hardware |
| Location | own infrastructure · EU · outside EU (greyed out and struck if the residency rule excludes it, with the rule named) |
| Eligible | evaluation passed (date) / not evaluated |
| Calculability | chips: count *upper bound*, cap *hard/soft*, kinds *in·out·read·write* |
| Price / 1M tokens | input · output · cache read · cache write; "unpriced" in red |
| Limit status | a bar per limit: rpm and tpm used in the current minute; subscription window share used with reset time; "cooling down until 14:32" |
| Health | last 429 (time, `Retry-After`), conformance M-01…M-04 with date, removal-test verdict (*changed*/*broke*/*untested*) |

**Right panel — "Why this route".** The policy in plain sentences ("cheapest eligible member
that the step's exactness and data class permit; next on limit or failure"), today's
fallbacks taken with their reason and count, blocked time booked to `limit.provider` today,
and the latest maturation proposal for this purpose ("`local-small` passed evaluation for
*triage*; estimated saving 62 % — propose").

**Footer — budgets of the units using this purpose.** A tree tenant → department → team with
spent / reserved / remaining, a forecast band, and the promise per kind ("held per step",
"as estimate", "window share only"). No per-person rows (principle 14).

**States to mock.** All green; one member at its rpm limit (amber bar, chain shows the
fallback active); a model in the chain missing from the price table under a currency budget
(red, "currency budget cannot be held for this member"); a member excluded by residency.
Phone width: purposes become a dropdown, the chain becomes cards, right panel folds below.
