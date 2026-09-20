# Anchors: the shipped default

This page is a template. It is the anchor configuration a new tenant inherits when nothing else
is configured. It is product: safe settings, written so that another organisation can adopt them
and change them. The configuration of the tenant that is the Taktus project itself is a separate
file, [anchors.taktus.md](anchors.taktus.md), and is not product.

An **anchor** keeps an act with a person regardless of how autonomously the rest of the work runs
(CLAUDE.md §8, ADR-0008, ADR-0022). This page makes anchors concrete enough to test a single
question against. It answers one question: **who decides this, and what is recorded.**

Two roles appear throughout. The **owner** is the person who owns the tenant: for an
organisation, the person named in its configuration; for this repository, the person named in
`.github/CODEOWNERS`. The **operator** is whoever does the work: a person doing it by hand, or
Taktus at autonomy level 3 or 4, or a session working in a repository.

---

## 1. Four modes

Every question falls into exactly one mode. The mode says who decides and what is written down.

| Mode | Who decides | What is recorded | Where |
|---|---|---|---|
| **1** | the operator, without notice | nothing beyond the change itself | the pull request, the run, the code comment |
| **2** | the operator, and records a notice | what was decided, on what evidence, what was considered, and which entry of this page permits it | a **notice record** in the decision register, `NTC-NNNN` (ADR-0017 §2a) |
| **3** | the owner; the operator prepares | a decision request in the seven-section shape, with a worked opinion — context, options, a recommendation with its reason — never a bare question | a **decision request**, `DEC-NNNN` (ADR-0017 §4) |
| **4** | the owner; the operator supplies data | the data the owner asked for, and the owner's decision once made | a decision record, `DEC-NNNN`, written from the owner's answer |

The difference between mode 3 and mode 4 is who does the thinking. In mode 3 the operator
works the question through and the owner reads a recommendation. In mode 4 the question is the
owner's own — a price, a licence, the basis on which money is counted — and the operator's part
is to supply what the owner needs to think, not a recommendation.

**Mode 2 is not "mode 1 with a note".** A notice is a record with a fixed shape and a gate. It
exists because a decision that is merely reported in a pull request disappears with the pull
request. A notice that weakens a gate carries, in the record itself, the evidence that the gate
had no value. "It was in the way" is not evidence.

---

## 2. The default entries

Each entry has an identifier: `M<mode>.<number>`. A tenant's own configuration refers to
entries by identifier and may move an entry to another mode, add entries, or remove entries
from modes 1 and 2. Entries in modes 3 and 4 that carry a legal or a correction anchor can be
narrowed but not removed (governance.md §2).

### Mode 1 — the operator decides, no notice

| Entry | The operator decides |
|---|---|
| M1.1 | **Naming, placement and layout** inside a documented structure. |
| M1.2 | **Ordering** of work inside an agreed scope. |
| M1.3 | **Which library or tool implements an agreed interface**, where the interface is documented and the choice does not add a dependency the whole product inherits. |
| M1.4 | **Fixing a documentation defect** in the tenant's own documents: an ambiguity, a contradiction, a statement that turns out to be wrong. The correction is recorded as a `DEFECT` record (ADR-0017 §2). If the correction would change what the software does, it is not a documentation defect and mode 3 applies. |
| M1.5 | **The wording of documentation** that states something already decided. |
| M1.6 | **Test strategy and fixtures** for an agreed scope. |

### Mode 2 — the operator decides and records a notice

| Entry | The operator decides and records |
|---|---|
| M2.1 | **Restructuring documentation** without changing what it says. |
| M2.2 | **A change of test strategy** and what the tests now cover. |
| M2.3 | **Weakening or removing a gate**, only where the notice demonstrates that the gate has no value. A *gate* is a check that must pass before a change is accepted. Narrowing what a gate looks at, adding an exception to it, or removing it weakens it. Making a gate correct without making it weaker is mode 1. |

### Mode 3 — the operator prepares, the owner decides

| Entry | The owner decides, with a worked opinion in hand |
|---|---|
| M3.1 | **Scope**: what belongs in a milestone and what does not. |
| M3.2 | **Accepting or rejecting a feature**, whoever proposed it. |
| M3.3 | **Assigning work to a version.** |
| M3.4 | **Any change to the substance of an accepted architecture decision.** An architecture decision record states a decision, the alternatives rejected and the consequences. Changing what was decided is the owner's call in the shipped default. |
| M3.5 | **Anything that would break a published contract**: a schema, an interface or a format that a third party already relies on. |
| M3.6 | **Preparing a release**: when a version is cut, tagged and put into operation. |
| M3.7 | **Anything published under the tenant's name**: public statements, claims, a public namespace. |
| M3.8 | **A new dependency the whole product inherits** — what the product itself needs in order to run. |
| M3.9 | **Raising an autonomy level** of a process or an action class (governance.md §1). |
| M3.10 | **Raising or lowering a limit**: a budget, a quota, a resource bound. |
| M3.11 | **A retroactive correction after the effect has left the system** — the correction anchor (ADR-0022). Correcting something nobody outside has seen is not in this entry. |
| M3.12 | **Binding a model purpose to a provider.** A process names a purpose, never a product; which provider serves the purpose is configuration, and changing it is this entry. |
| M3.13 | **Choosing a method within an exactness class**, where more than one method is admissible for the class. |
| M3.14 | **Routing between approved models**: which of several configured models a purpose uses, and when. |

### Mode 4 — the owner decides, the operator supplies data

| Entry | The owner's own question |
|---|---|
| M4.1 | **The licence.** |
| M4.2 | **The price**, and what is charged for. |
| M4.3 | **The accounting basis**: the unit in which work is counted and the weights behind it. |
| M4.4 | **Every legal anchor** of the tenant: signature, payment release above a threshold, a filing, a termination, a notification, a contract (governance.md §2). |

---

## 3. The same anchor resolves differently per tenant

An entry names *what* is decided. *Who* decides it is the tenant's configuration. The clearest
case is M3.4, a change to an accepted architecture decision. In a managed product that change is
the owner's call, because the owner carries the consequences and did not write the decision. In
the Taktus project it is the operator's call for as long as the vision holds, because the
session that changes the decision is the one that reads every consequence — and the owner's
anchors on scope, features and releases still hold. Both configurations are right. Neither is
the default for the other.

---

## 4. Neither list

A question that fits no entry is itself worth recording. It is not decided alone and it is not
escalated as if it were the owner's. It is raised as a `NON-BLOCKING` decision request
(ADR-0017 §3), the work continues on a provisional answer, and the request proposes which mode
the question belongs in. The owner's answer then extends this page or the tenant's own. The lists
grow by use.

---

## 5. How to test a question against this page

1. Read the tenant's own configuration first. It overrides this page entry by entry.
2. Find the entry in mode 3 or 4 that makes it the owner's call. If there is one, write a
   decision request and cite the entry.
3. If there is none, find the entry in mode 2. If there is one, decide, write the notice, and
   move on.
4. If there is none, find the entry in mode 1. If there is one, decide and move on.
5. If there is none anywhere, §4 applies.
6. If the question is "which of two readings of a document is right", stop: that is a
   documentation defect (M1.4), not a decision. Correct the document.
