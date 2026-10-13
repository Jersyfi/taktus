# Decision register

The decisions of the Taktus project itself: what the owner was asked, what was answered, what
was raised as a decision and turned out not to be one, and what a session decided on its own
and gave notice of. The mechanism is ADR-0017. Which questions reach the owner is stated in
four modes: [anchors.md](anchors.md) is the shipped default any tenant inherits, and
[anchors.taktus.md](anchors.taktus.md) is the configuration of this tenant, the Taktus
project. The template for a request is [TEMPLATE.md](TEMPLATE.md); the template for a notice
is [TEMPLATE-NOTICE.md](TEMPLATE-NOTICE.md); the template for a needs request is
[TEMPLATE-NEED.md](TEMPLATE-NEED.md).

The category `DEFECT` is a *documentation defect*: a fault in what the repository says, corrected
and recorded, never asked. A wrong result produced by a run is a *result defect* (ADR-0021) and
never appears in this register.

`open/` holds requests that wait for an answer, and needs that wait to be provided. A request
leaves `open/` in the same commit that creates its record here. `make gate-decisions` checks
both, the notices, and the needs.

A **notice**, `NTC-NNNN`, is the record of a mode-2 decision (anchors.md §1): the session
decided, nobody approves, and the record states what was decided, on what evidence, what was
considered and which entry permits it. Every notice carries a **kind** — `restructuring`,
`test-strategy`, `gate-weakened`, `behaviour-change`, `unlisted` — so that the register reads by kind and
a weakened gate is never buried among behaviour changes (DEC-0014). A notice that weakens a
gate carries the demonstration that the gate had no value, in the record itself.

A **needs request**, `NEED-NNNN`, is the record of something only the owner can provide — a
credential, an account, access to a system, a purchase, an action on a server, information about
an environment (ADR-0028). It is raised when it becomes foreseeable, not when it blocks; raising
it is mode 2 (entry M2.5), providing it is the owner's act. An open need is under `open/` with an
issue labelled `needs-owner`; a provided need is a record here with its outcome. What is open is
printed by `make status` and carried by every pull request description (DEC-0026).

## The index

`make register` prints the index. It lists every provided need, every notice and every record,
each in its own table, generated from the files here. The index is stored nowhere a pull
request edits. Until 2026-10-13 it was three tables in this file. Any two pull requests that
each added a record then added a row at the same place and conflicted on it (DEC-0189 rule 6,
DEC-0026). The tables as they stood are in this file's history. `make gate-decisions` fails
this file when it stores a row again.

## Numbers

A number is reserved before the record is written: `make reserve KIND=DEC`, `KIND=NTC` or
`KIND=NEED`. The tool creates the ref `refs/register/<PREFIX>-<NNNN>` on the repository's
remote. A ref is created once: of two sessions that try the same number, exactly one gets it,
and the other is given the next. A number reserved and never written leaves a gap. A gap means
nothing, and a number is never reused.

A record keeps its number from the moment it is written. Nothing renames it when it merges, so
an issue, a commit or a pull request may name it at once. Two pull requests that each add a
record merge in either order without a conflict. `make gate-decisions BASE=origin/main` fails a
record the branch adds whose number is not reserved; CI runs it on every pull request.

A number a branch took before reservations existed is reserved as it is, for example with
`make reserve ID=NTC-0207`. The tool refuses a number that `main` or another reservation
already holds.
