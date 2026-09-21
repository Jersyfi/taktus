# Anchors of the Taktus project

This page is the anchor configuration of one tenant: the Taktus project itself, the repository
you are reading. It is not product. It overrides the shipped default, [anchors.md](anchors.md),
entry by entry, and the four modes and the entry identifiers are the default's. Read the default
first; it explains the modes and the roles.

The owner is the person named in `.github/CODEOWNERS`. The operator is the session doing the
work, human or machine. Every session in this repository tests every question against this page
before raising it (CLAUDE.md §8). Raising a mode-1 or mode-2 question to the owner is a fault in
the request, not caution. Deciding a mode-3 or mode-4 question alone is a breach.

The entries below are the owner's own answers, given on 2026-09-21, recorded here in the
default's identifiers. Where the same entry sits in a different mode here than in the default,
that is intended: the same anchor resolves differently per tenant (anchors.md §3).

---

## Mode 1 — the session decides, no notice

| Entry | The session decides | Where it is visible |
|---|---|---|
| M1.1 | **Naming, placement, module layout** within `docs/architecture/project-structure.md`. | the pull request description; the structure document if the structure gains a rule |
| M1.2 | **Ordering** of work inside an agreed scope. | the pull request description |
| M1.3 | **Which library implements a documented port.** | `docs/architecture/project-structure.md` and the technology table in `README.md` |
| M1.4 | **Fixing a documentation defect** in the repository's own documents. Recorded as a `DEFECT` record; an ADR amendment where an ADR is involved (ADR-0017 §2). If the correction would change what the software does, it is a decision and the mode of that decision applies. | the `DEFECT` record |
| M1.5 | **The wording of documentation** about something already decided. | the document |
| M1.6 | **Test strategy and fixture design** for an agreed scope. | `tests/README.md` and the tests |
| M1.7 | **Milestone scope: which feature lands in which milestone.** The default keeps this with the owner (M3.1). Here it is the session's, because the roadmap states the completion criteria and the session is the one holding the work against them. | `docs/roadmap.md` |
| M1.8 | **Version assignment once a feature is accepted.** The default keeps this with the owner (M3.3). Accepting the feature is still M3.2. | `docs/roadmap.md` |
| M1.9 | **A change to the substance of an accepted ADR, as long as the vision holds.** The default keeps this with the owner (M3.4). Here it is the session's while the change keeps every guiding principle (CLAUDE.md §5), keeps the four requirements of ADR-0013, and touches no entry of mode 3 or 4 of this page. A change that would touch one of those is that entry's decision. The record is the amendment itself, in the ADR, with its date and reason. | the ADR |

## Mode 2 — the session decides and records a notice

| Entry | Kind | The session decides and records | The record |
|---|---|---|---|
| M2.1 | `restructuring` | **Documentation restructuring** without changing what the documents say. | a notice, `NTC-NNNN` |
| M2.2 | `test-strategy` | **A change of test strategy** and what the tests now cover. | a notice, `NTC-NNNN`; `tests/README.md` says the same |
| M2.3 | `gate-weakened` | **Weakening or removing a gate, only where it is demonstrated that the gate has no value.** A notice suffices; approval does not. The notice carries the demonstration: what the gate looked at, what it would have caught, the evidence that it caught nothing and could catch nothing. "It was in the way" or "it was slow" is not a demonstration. A gate that is slow is a finding to report with its cost, not a gate to remove (CLAUDE.md §11). | a notice, `NTC-NNNN`, with the section "Why the gate had no value" |
| M2.4 | `behaviour-change` | **A change of what the software does, made inside an agreed scope**, that breaks no contract, moves no limit or autonomy level and says nothing public. Added by DEC-0014. The notice names the old behaviour, the new one and the reason the scope needed it; a change that would break a contract, move a limit or a level, or say something public is that entry's decision (M3.5, M3.10, M3.9, M3.7). | a notice, `NTC-NNNN` |

The kind is the default's vocabulary (anchors.md §1); the entry is this tenant's permission. A
notice carries both, and `make gate-decisions` fails when they do not match.
| M2.5 | **Raising a needs request** — a credential, an account, access, a purchase, an action on a server, information about an environment — when it becomes foreseeable (ADR-0028). The session decides that the need exists and raises it; nobody approves the raising. Providing it is the owner's act. The owner's brief of 2026-09-21 places it here. | the needs request itself, `NEED-NNNN`, under `docs/decisions/open/` with an issue labelled `needs-owner`, assigned to the owner |

## Mode 3 — the session prepares, the owner decides

The owner wants a worked opinion with context, not a question. Every request in this mode has
the seven sections of ADR-0017 §4, two or three options, one recommended with its reason.

| Entry | The owner decides |
|---|---|
| M3.2 | **Accepting or rejecting a feature**, with the session's worked recommendation. A proposal from a session, an issue or the owner's own notes is a proposal until the owner accepts it. |
| M3.5 | **Anything that would break a published contract.** The contracts under `contracts/` are published once a version of Taktus that uses them is released; until then `v1` may still move (ADR-0019). |
| M3.6 | **Preparing a release**: cutting, tagging, putting into operation. |
| M3.7 | **Anything published under the project's name**: `README.md` claims, website copy, public statements, the contract namespace `https://taktus.eu/contracts/` (ADR-0019). |
| M3.8 | **A new dependency at integration-code tier 1** — what Taktus itself needs in order to run: database, queue, secret store, telemetry, reference workers (`docs/architecture/contracts.md` §7). Tier 2 is not in this entry. |
| M3.9 | **Raising an autonomy level** of a process, including the project's own processes. The session proposes the raise with evidence (governance.md §1; ADR-0026). |
| M3.10 | **Raising or lowering a limit**: a budget, a quota, a compute bound, a safety margin (ADR-0005). |
| M3.11 | **Retroactive correction after the effect has left**: a tagged release, a published package, a public statement, a contract a third party relies on (ADR-0022). Correcting an unmerged branch, or `main` before a release, is not in this entry: nothing has left. |
| M3.12 | **Binding a model purpose to a provider.** |
| M3.13 | **Choosing a method within an exactness class**, where the class admits more than one. |
| M3.14 | **Routing between approved models.** |

## Mode 4 — the owner decides, the session supplies data

| Entry | The owner's own question |
|---|---|
| M4.1 | **The licence** (ADR-0012). |
| M4.2 | **The price.** |
| M4.3 | **The accounting basis**: the Takt, its weights and what is charged (ADR-0010). |

The Taktus project has no legal anchor of its own yet (M4.4 of the default is empty here): the
repository signs nothing, pays nothing and files nothing. The entry returns the moment it does.

---

## Neither list

A question that fits no entry is not decided alone and not escalated. It is raised as a
`NON-BLOCKING` decision request (ADR-0017 §3), the work continues on a provisional answer, and
the request proposes which mode the question belongs in. The owner's answer then extends this
page. The lists grow by use.

## How to test a question

1. Find the entry in mode 3 or 4. If there is one, it is a decision request; cite the entry
   in section 2 of the request.
2. If there is none, find the entry in mode 2. If there is one, decide, write the notice, and
   move on.
3. If there is none, find the entry in mode 1. If there is one, decide and move on.
4. If there is none anywhere, *Neither list* applies.
5. If the question is "which of two readings of a document is right", stop: that is a
   documentation defect (M1.4), not a decision. Correct the document.

## History

The first version of this page, until 2026-09-21, had two lists: what the owner decides (rows
`O1` to `O10`) and what the session decides (rows `D1` to `D6`). The owner's answers fell almost
entirely between them, which is why there are four modes now. Records written before that date
cite the old rows; `O1`/`O3` are now M1.7/M1.8, `O2` is M3.2, `O4` is M1.9, `O5` is M3.6, `O6`
is M4.1 to M4.3, `O7` is M3.7, `O8` is M3.8, `O9` is M2.3, `O10` is M3.11, and `D1` to `D6`
are M1.1 to M1.6. The restructuring is recorded as NTC-0001.

M2.4 was added on 2026-09-21 from the owner's answer to DEC-0014, the first question raised
under *Neither list*; the same answer gave every notice its kind.
