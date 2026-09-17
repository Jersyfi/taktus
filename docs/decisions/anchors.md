# Anchors of the Taktus project: what is the owner's call

This page answers one question: **which questions reach the owner, and which are decided by
whoever is doing the work.** It applies to every session in this repository, human or machine.

It is the concrete form of two general statements. CLAUDE.md §8 says that *strategic anchors* —
direction, scope, releases, licensing, anything public — stay with a person regardless of how
autonomously the rest of the work runs. ADR-0008 makes that a mechanism: an anchor halts work and
raises a decision request. Neither text is concrete enough to test a single question against.
This page is.

The owner is the person named in `.github/CODEOWNERS`.

---

## 1. The owner decides

For the Taktus project itself, these questions reach the owner. Nobody else answers them, and
work that depends on the answer does not pretend the answer is known.

| # | The owner decides | What that means in practice |
|---|---|---|
| O1 | **Scope** — what belongs in a milestone and what does not | A *milestone* is one of the versions in `docs/roadmap.md`. Adding a piece of work to a milestone, or taking one out, is the owner's call. |
| O2 | **Accepting or rejecting a feature**, whoever proposed it | A proposal from a session, an issue or the owner's own notes is still only a proposal until the owner accepts it. |
| O3 | **Assigning work to a version** | Moving work between milestones, or deciding which version ships a change. |
| O4 | **Any change to the substance of an accepted ADR** | An *ADR* (architecture decision record, `docs/adr/`) states a decision, the alternatives rejected and the consequences. Changing what was decided is the owner's call. Correcting a documentation defect in how it was written is not — see §2, D6. |
| O5 | **Releases** | When a version is cut, tagged and put into operation. |
| O6 | **Licensing, pricing, the accounting basis** | The licence of the repository (ADR-0012), what is charged and how, and the unit in which orchestrated work is counted (ADR-0010). |
| O7 | **Anything published under the project's name** | Website copy, claims in `README.md`, public statements, and the *contract namespace* — the public address under which the machine-readable contracts in `contracts/` are identified (ADR-0019). |
| O8 | **A new external dependency at integration-code tier 1** | *Tier 1* is what Taktus itself needs in order to run: database, queue, secret store, telemetry, reference workers (`docs/architecture/contracts.md` §7). Adding one is a dependency the whole product inherits. Tier 2 — what Taktus conducts on behalf of a customer — is not in this list. |
| O9 | **Anything that would weaken a gate** | A *gate* is a check that must pass before a change is merged: `make gates` lists them. Removing a gate, narrowing what it looks at, or adding an exception to it weakens it. Making a gate correct without making it weaker (for example: reporting green when there is nothing to check) is not in this list. |

---

## 2. The session decides, and records it

These are never escalated. The person or session doing the work decides them and writes the
decision down where it is visible — in the pull request description, in a code comment, or in the
documentation the change touches. Raising one of these as a question to the owner is a fault in
the request, not caution.

| # | The session decides | Where it is recorded |
|---|---|---|
| D1 | **Naming, file placement, module layout** within the documented structure (`docs/architecture/project-structure.md`) | the pull request description, or the structure document if the structure itself gains a rule |
| D2 | **Which library implements a documented port** | `docs/architecture/project-structure.md` and `README.md`, technology table |
| D3 | **Test strategy and fixture design** | `tests/README.md` and the tests themselves |
| D4 | **The wording of documentation** that states an already-decided thing | the document |
| D5 | **How to sequence work** inside an agreed scope | the pull request description |
| D6 | **Correcting a documentation defect** — an ambiguity, a contradiction, a statement in the repository's own documents that turns out to be wrong | an ADR amendment where an ADR is involved, and a DEFECT record under `docs/decisions/` (ADR-0017 §2) |

D6 has one exception. If correcting the documentation defect would change what the software actually does — not
only how it is described — that change is a decision and follows the rules of ADR-0017.

---

## 3. Neither list

A question that fits neither list is itself worth recording. Raise it as a NON-BLOCKING decision
request (ADR-0017), continue on a provisional answer, and propose in the request which list the
question belongs in. The owner's answer then extends this page.

---

## 4. How to test a question against this page

1. Find the row in §1 that makes it the owner's call. If there is one, it is a decision request;
   cite the row number in the request (ADR-0017, section 2 of the request).
2. If there is none, find the row in §2. If there is one, decide, record, and move on.
3. If there is none in either list, §3 applies.
4. If the question is "which of two readings of a document is right", stop: that is a documentation defect (D6),
   not a decision. Correct the document.
