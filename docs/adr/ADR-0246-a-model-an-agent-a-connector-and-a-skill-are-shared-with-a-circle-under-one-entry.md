# ADR-0246 — A model, an agent, a connector and a skill are shared with a circle under one entry

**Status:** accepted · extends ADR-0163 (shared agents), ADR-0162 (skills), ADR-0116 (purpose
chains) and ADR-0039 (from level 3 a step runs only on a verified adapter) · UC-8.6, UC-8.7,
UC-8.8, UC-14.3 · DEC-0228

## Context

The catalogue holds four kinds of thing a team may use: models (UC-8.6), agents (UC-8.7),
connectors (UC-8.8) and skills (UC-14.3). The four use cases ask the same of each. An entry is
provided centrally. It names an owner, a purpose and a maturity. It is shared with a **circle**,
which is one unit of the organisation's structure. It is visible and usable inside that circle
and nowhere else. Its use can be evaluated per circle. A person's own use is visible to that
person, and anyone else sees it only aggregated.

The tree already holds the parts that do not depend on sharing. A configured model has a
location and a billing kind (ADR-0116, `contracts/model/v1`). A connector and a worker have a
derived maturity (ADR-0044). A shared agent has a core and role profiles (ADR-0163). A skill has
a lifecycle (ADR-0162). An identity carries its place in the structure as a path, from the
tenant through department or group and team to project (`Identity.org_path`, ADR-0020). Every
run carries the identity it runs as and that identity's unit (`Run.org_unit`, ADR-0166).

What was missing is the record that says who may use an entry, and the rule that holds a run to
it.

## Decision

### 1. One record per entry: the share

A **share** (`catalog/domain/model/shares.py`, `CatalogueShare`) is kept under
`<kind>:<subject>`. The kind is `model`, `agent`, `connector` or `skill`. The subject is how the
rest of the instance names the entry: the adapter identifier of a model or a connector
(`model.local`, `connector.tickets`), the name of an agent or of a skill. Every share names:

- its **owner**: the identity answerable for the entry;
- its **purpose**, in words;
- one or more **circles** (§2).

A model's share also names its **data-protection classification**, which is where it processes
data (`own`, `eu` or `elsewhere`, as UC-11.1 and ADR-0116 name locations), and its **cost
model**, which is the billing kind of `contracts/model/v1` (`per_token`, `per_window`,
`per_hardware_time`). A model the organisation trained names its **version**, which is the
digest of the model file, and its **evaluation history**: the evaluations that admitted it
(ADR-0114 §4). A share that lacks a field its kind requires is refused, and the refusal names
every missing field. Nothing is shared without them.

The **maturity** of an entry is never stated on the share. It is read where it is kept. For a
model or a connector it is the adapter's maturity record (ADR-0044). For an agent it is the
state of its active core (ADR-0163). For a skill it is its stage (ADR-0162). An entry shows the
maturity it has when it is read.

### 2. A circle is a unit of the structure, or one person

A circle is either a path of the structure or one identity:

- **A path** — `acme`, `acme/sales`, `acme/sales/north` — admits every identity whose own
  path starts with it. The whole company is the tenant's path. A family is a tenant of its own.
  A department, a team or a project is a longer path.
- **One identity** — `identity:<id>` — admits that identity alone. It is how a person keeps an
  entry to themselves.

An identity is inside a share when it is inside any one of the share's circles.

### 3. Outside the circle, an entry is neither seen nor used

- **Listing.** A reading of the catalogue for a viewer leaves out every share the viewer is not
  inside. Nothing says that it exists.
- **A run on a model.** The route through a purpose's chain (ADR-0116 §4) passes over a member
  whose share does not admit the run's identity. The provenance names it with the reason
  `not_shared`, beside `residency`, `exactness` and `cooling_down`.
- **A run on a connector.** A connector call of a run whose identity is outside the
  connector's share is refused before it is made. It is recorded as `frame.refused`, outcome
  `outside_circle`, and the step fails without retrying (ADR-0130).
- **A shared agent.** A call by an identity outside the agent's share is refused before a run
  starts, with `agent.refused`, outcome `outside_circle`.
- **A skill.** A skill version a run may pin is one the run's identity is inside the share of.
  Where none of the skill's production versions is shared with the identity, the skill is not
  handed to the step.

An entry that has no share is the tenant's, as the operator configured it. It is usable by
every identity of the tenant, as before this decision. Sharing narrows an entry. It never
widens what the operator's configuration allows.

### 4. Sharing is recorded, and a person's own skill is shared only by that person

Sharing, changing the circles of, and withdrawing a share are each a ledger entry:
`catalogue.shared`, `catalogue.withdrawn` and `catalogue.share_refused`. Each names the entry in
`adapter` for a model or a connector, in `refs.agent_id` for an agent and in `refs.skill_id`
for a skill. The person who acted is `refs.actor`. The reason is the outcome.

A skill drawn from one person's own use (`SkillOwnership`, ADR-0162) is shared only by that
person. Any other actor, an administrator included, is refused with outcome `not_owner`. Only
a skill at stage `approved` or `production` can be shared (UC-14.3). Only an agent whose core
is active can be shared, which means a person accepted it (§6 of ADR-0247).

### 5. Withdrawing a model or a connector waits for its removal verdict

Withdrawing a model or a connector from a circle where processes use it is a removal in the
sense of UC-8.9. The withdrawal takes effect only when the adapter's maturity record holds a
removal test. The withdrawal's ledger entry quotes that verdict as its outcome: `changed`,
`untested` or `broke`. A withdrawal with no removal test on record is refused with outcome
`no_verdict`. A withdrawal whose verdict is `broke` is refused unless the person confirms it in
the same act, and then its outcome is `broke`. The person withdrawing it knows the verdict
before the withdrawal takes effect either way.

### 6. Use is counted per circle, and a person's own use only for that person

A reading of an entry's use counts its calls from the ledger. For a model or a connector these
are the steps it served: every `step.finished` entry that names the adapter. For an agent they
are the `agent.called` entries. For a skill they are the runs that
pinned it. Each call is attributed to the run that made it, and through the run to its
organisational unit. The reading returns, for a viewer:

- the calls per organisational unit, with no identity in them;
- the viewer's own calls, counted over the runs the viewer started.

It never returns another person's own count. This is principle 14 and ADR-0015 applied to the
catalogue.

## Alternatives

- **A share per kind, kept by each component's records.** The models would keep it in the
  configuration, the agents on their core, the skills on their version. Four records would then
  express one rule four times, and they could disagree. Rejected: one rule, one record.
- **A circle as a list of identities.** It would not follow the structure: a person who joins a
  team would not see what the team shares until somebody added them. Rejected: UC-1.4 makes the
  structure the place where membership is kept.
- **Hide an unshared entry by the operator's configuration alone.** The operator would have to
  configure one adapter per team. That is the "further setup" UC-8.8 rules out.
- **Withdrawal without a verdict, with a warning.** A warning is read after the fact. UC-8.6
  asks for the verdict to be known before the withdrawal takes effect.

## Consequences

- `catalog`: the share, its rules (`domain/service/shares.py`) and its use case
  (`application/service/shares.py`), with the table `catalogue_share` (migration 0103).
- `run`: the port `Shares` (`run/ports/shares.py`). The engine asks it on a model's route and
  before a connector call. Without it nothing is narrowed, which is what the engine did before.
- `taktusctl catalogue share`, `withdraw`, `shares` and `use`.
- `contracts/shared/v1/Provenance.json`: the route's skip reason `not_shared`, an added value.

## Where this promise ends

- A circle follows the identity's path as the identity record holds it. A person moved to
  another team keeps what the old path admitted until the identity record is changed.
- Use per organisational unit can still point to a person when a unit has one member. The
  reading does not suppress small units. Whoever sets up the structure decides how fine it is.
- A share narrows who may use an entry inside Taktus. It does not change the source system's
  permissions. Those are the caller's credential's (ADR-0247).
- The use of a model or a connector is counted by the steps it served. A step that called a
  connector twice counts once. A call that a worker made with its own tools is not counted
  here.
- An entry without a share stays usable by the whole tenant. Sharing is opt-in per entry, so
  an operator who never shares anything sees no change.
- Withdrawal does not remove the adapter from the configuration. It removes the circle's access.
  The operator removes the adapter.
