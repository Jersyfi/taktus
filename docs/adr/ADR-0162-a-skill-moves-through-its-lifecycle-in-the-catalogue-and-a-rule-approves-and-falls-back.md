# ADR-0162 — A skill moves through its lifecycle in the catalogue, and a rule approves it and falls it back

**Status:** accepted · extends ADR-0113 (skills are `SKILL.md`), ADR-0134 (evaluation cases) and ADR-0030 (the rehearsal) · issue #646, UC-14.2, UC-4.4, DEC-0028, NTC-0246

## Context

ADR-0113 chose the format of a skill: a directory with a `SKILL.md`, under `skills/` in a
bundle, named by a step in its `work`. It left everything else open. Nothing loaded a skill,
versioned it, evaluated it or handed it to a step.

UC-14.2 asks for a lifecycle under governance. A skill is drafted, evaluated and rehearsed,
approved, put into production, measured, and falls back when it gets worse. Approval is a
person's at autonomy levels 1 to 3. At level 4 it is automatic after n passed evaluations, and
DEC-0028 gives n a floor that no configuration can go below, higher for a skill an `exact` step
uses. UC-4.4 asks that a way of working that recurs in corrections becomes a draft skill.

Three words are used below. A **skill version** is one content of one skill, named
`<name>@<version>`. A **round** is one evaluation of a skill version: an evaluation on the
cases of every process that uses the skill, held to ADR-0134's rules. A **pin** is the version
of a skill that one run uses, fixed when the run is created.

## Decision

### 1. The catalogue keeps a skill version beside its file

The catalogue component keeps one record per skill version: `SkillVersion`. It holds what
ADR-0113 keeps beside the file, never in it:

- the parsed file: name, description, instructions, the other front-matter fields as they
  are, and the digest of the directory's content;
- the **origin**: what it was drawn from — a bundle, recurring corrections, a person's own
  use — and the runs, the processes and the steps it was drawn from;
- whether it is **owned**: drawn from one person's own use. Who that person is, is kept in a
  record of its own, `SkillOwnership`, so that no record holds a person beside a score;
- the **stage**, its history, its rounds, its dry run, its measurements and its predecessor.

A version once registered never changes its file. A different content under the same version
is refused, as a process version is (#377).

**A skill names no person.** The origin names runs, processes and steps only. A draft drawn
from one person's own use names that person as its owner and is private: only the owner sees
it, and only the owner's act shares it. A private draft is not evaluated, approved or handed to
any run. Once shared, the owner is still recorded, and nothing shown to anyone else names them
(principle 14).

### 2. The stages, in order

| Stage | Reached when | Ledger |
|---|---|---|
| `draft` | registered from a bundle, or drafted from recurring corrections | `skill.drafted` |
| `evaluated` | a round passed and its dry run completed | `skill.evaluated` |
| `approved` | a person approved, or the rule approved at level 4 | `skill.approved` |
| `production` | the takeover instructions of every process using it name it | `skill.produced` |
| `retired` | a successor reached production, a fallback, or a person retired it | `skill.retired` |

A stage is reached only from the one before it. `retired` is reached from any stage. A fallback
brings the predecessor back from `retired` to `production`, recorded as `skill.produced` with
outcome `fallback`. Every change is one ledger entry with `refs.skill_id`, in the same
transaction as the record. An act that the order refuses is `skill.refused`, with the reason as
outcome, and the record does not change.

### 3. A round is an evaluation on the cases of the processes that use the skill

A process uses a skill when a step of its active version names it in `work.skills`. A round
starts, for each using process with evaluation cases, an ADR-0134 evaluation of purpose `skill`.
Both sides run the active version on every case as rehearsals. The active side runs with the
skill as it is in production, or with no version of it where none is. The proposed side runs
with the evaluated version pinned. The verdict is the rule of a change (ADR-0134 §4): `passed`,
`regressed` or `incomplete`, against the tenant's tolerance.

A round **passed** when every evaluation passed. A skill that no using process can evaluate has
no round, and stays a draft: a draft without an evaluation is never approved.

The **dry run** is the proposed side of the first passed round. It completed when every case run
of that side finished. A rehearsal acts on nothing outside (ADR-0030), so the dry run does not
either.

### 4. Approval by the autonomy level, and the floor for n

The level is the lowest level among the active versions of the processes that use the skill.
At levels 1 to 3 a person approves. The approval names the person as actor of `skill.approved`.

At level 4 the rule approves once the most recent n rounds of the version all passed. A round
that did not pass resets the count. The tenant's **skill policy** holds n:

- `floor`: the smallest n for a skill no `exact` step uses. Shipped **11**.
- `exact_factor`: what the floor is multiplied by for a skill an `exact` step uses. Shipped
  **2**, so **22**.
- `n`: the tenant's own n, at least the floor. A skill an `exact` step uses needs n times the
  factor.

A policy below a shipped value is refused, and so is an `n` below the floor. The
derivation of the numbers is NTC-0246. At level 4 the next round starts once a day, until the
count is reached.

### 5. A skill guides, and the step's class still bounds the result

The run pins each skill a step names when the run is created: the version in production, or
the version an evaluation's side binds (`Run.skills`). A skill with no version in production is
not handed over, and the step runs without it. The run hands the pinned skill's instructions to
the step in its brief. A step on a language model receives them before its system text. A
worker step receives them after its goal. Nothing else of the step changes. Its method, its
checks and its exactness class are those of the version (ADR-0014). A skill never widens a
frame: `allowed-tools` is not read (ADR-0113 §1).

### 6. Production updates the takeover instructions

Before a version is used for real, the takeover instructions of every process using it name
that version (UC-6.3). No process version carries stored takeover instructions yet. The skill
part of them is therefore derived. For each step of a process, the catalogue names the skills
the step uses, by version, with their instructions. `taktusctl skill takeover` prints it, and a
person can run the step from it. Putting a version into production records `skill.instructed`
for each using process, with `refs.process_version`, before `skill.produced`.

### 7. A rule falls a worse version back

A version in production is measured. Its rounds give its score on the cases. A drift
evaluation of a using process whose runs pinned it gives its score in operation. The newest
measurement is compared with the predecessor's last one. When it is lower by more than the
tenant's tolerance (ADR-0134 §8), the version is retired with outcome `fallback`. The
predecessor returns to production. The rule reads numbers; no language model takes part
(ADR-0023).

### 8. Recurring corrections become a draft skill (UC-4.4)

A look reads the tenant's corrections: `step.corrected`, and `proposal.decided` with outcome
`corrected`. A step of a process corrected in at least **3** distinct runs becomes a draft
skill named after the process and the step. Its origin names those runs and the step. Its
instructions say what recurred and where, for a person or a worker to write out as a new
version. The rule is counting. It never reads who corrected, and the draft names no person.

### 9. Bundles carry their skills

`skills/<name>/SKILL.md` beside a bundle's processes is parsed by the catalogue's rule
(`parse_skill`). `taktusctl skill register PATH` registers every skill below a directory as a
draft. `taktusctl bundle check` checks them as well: the front matter, and the name against
the directory. Registration holds `work.skills` to being a list of skill names.

### 10. Method and exactness

| Part | Method | Exactness | Reason | Rejected |
|---|---|---|---|---|
| the order of stages | `rule` | `exact` | a stage follows from the record and the act, the same way every time | `llm` — a stage change is a governed act |
| approval at level 4 | `rule` | `exact` | counted rounds and a configured n, recomputable by a person (ADR-0023) | `statistics` — a test needs more rounds than a skill carries; `llm` |
| the fallback | `rule` | `exact` | two recorded scores and the tolerance | `llm` — UC-14.2 forbids it |
| a draft from corrections | `rule` | `exact` | a count of distinct runs per step | `ml` — no labelled data; `llm` — it could describe a person |
| the parsing of `SKILL.md` | `rule` | `exact` | the open format's own rules | none |

## Alternatives

- **The stage in the file's front matter.** Rejected by ADR-0113 §1: the exported skill would
  carry fields no other reader knows.
- **A skill reaching production on its first passed round at level 4.** Rejected by DEC-0028:
  one evaluation is too little evidence for an unattended change.
- **The floor as a constant without configuration.** Rejected: UC-14.2 keeps n configurable
  above the floor.
- **Handing the newest approved skill to every run, unpinned.** Rejected: a run would change in
  the middle of a fallback, and its record would not say which know-how it used.
- **A skill round as a proposal of the process.** Rejected: a skill changes no step of the
  version, and a proposal would register a version for every skill.

## Consequences

- The catalogue gains `SkillVersion`, `SkillOwnership`, `SkillPolicy` and the rules in
  `domain/service/skills.py`, and the application service `SkillCatalog`.
- The process component gains purpose `skill` on `Evaluation`, and registration holds
  `work.skills`.
- The run component gains `Run.skills`, `StartRun.skills`, the control key `skills` and the
  port `Guidance`.
- The composition root gains `SkillLifecycle` (`composition/skills.py`), run by the scheduler's
  minute loop, and `taktusctl skill`.
- `LedgerRefs.skill_id`, and the kinds `skill.drafted`, `skill.shared`, `skill.evaluated`,
  `skill.approved`, `skill.instructed`, `skill.produced`, `skill.retired` and `skill.refused`.
- Migration 0090 adds the tables `skill_version`, `skill_ownership` and `skill_policy` and the
  column `run.skills`.

## Where this promise ends

The lifecycle governs skills that the catalogue knows. A step that names a skill with no version
in production runs without it, and nothing refuses the run. The run hands a skill over in the
step's brief only. An adapter whose agent reads skills in its own way receives them the same
way, and nothing hands it the skill's other files. A skill's scripts and references are kept by
digest, not served.

A round is only as good as the cases of the processes that use the skill. A process without
evaluation cases cannot evaluate a skill, and a skill used only there stays a draft. Rounds on
the same cases differ only where a model answers differently, so n rounds are n samples of the
same cases, not of new work. The floor bounds how likely a skill that fails often is approved
automatically, as NTC-0246 derives it. It does not bound how much worse such a skill is.

The level is read from the active versions as they are registered. A level lowered by rule
(ADR-0110) is not read here. A round costs what its runs cost, up to twice the version's budget
per case, once a day, and no budget bounds a skill's rounds as a whole.

The takeover instructions name a skill's version as the catalogue derives them. Until process
versions carry their own instructions (UC-6.3), nothing checks that a person has read them.
The fallback compares the newest measurement with the predecessor's last. A slow decline within
the tolerance per measurement is not seen. Recurring corrections are counted per step, not per
kind of correction, and the draft they produce holds what recurred, not yet how to do it.
