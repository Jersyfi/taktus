# DEC-0080 — The method of P-01's reconciliation

**Category:** NON-BLOCKING
**Raised in:** [#127](https://github.com/Jersyfi/taktus/pull/127), while implementing issue #71: the blueprint names a language model for the step a rule can now do
**Issue:** [#126](https://github.com/Jersyfi/taktus/issues/126)
**Needed by:** 2026-10-23
**Provisional answer:** Option A. P-01 Roadmap control runs with its reconciliation as a rule over the issue numbers the roadmap's items name, classed `exact`; `docs/roadmap.md` names the issues of its items. Marked in the bundle's header and in the step's rejected alternative, and in `blueprint.yaml`.

## 1. What this is about

*P-01 Roadmap control* is the process that holds the roadmap against the backlog. The roadmap
says, per version, what the version is to contain: a list of items. The backlog is the
repository's open issues, each in a version (a *milestone*). P-01 reads both every day and
reports where they disagree: an item of a version that no issue carries, and an issue in a
version whose items do not include it. It also reports an issue labelled `ready` that does not
meet the ready standard, and prints the backlog's order. It changes nothing; a person acts on
the report.

The step that matters here is the *reconciliation*: deciding which issue carries which item.
The blueprint that describes P-01 says a language model does it, because "no rule can express
it": items and issue titles are prose, and only a reader can tell that "the owner-facing
channel" and the issue "The owner-facing channel" are the same thing.

What was attempted: a rule can do it if the roadmap says which issue carries each item. This
pull request gives every item of the roadmap the numbers of its issues, `(#85)`, and makes the
reconciliation a rule over those numbers. Run on this repository's roadmap and open issues, the
rule finds no issue the roadmap does not place, and 24 items, all of later versions, that no
issue carries yet. That is the method the blueprint did not name, so it is asked.

## 2. Why you are being asked

Entry M3.13 of the Taktus project's anchors: "Choosing the method kind of a step — `rule`,
`statistics`, `ml`, `neural`, `llm`, `worker`, `human`, `wait` — where the step's exactness
class admits more than one kind." The blueprint classes the reconciliation `sourced`, which
admits both a rule and a model; replacing the model with a rule is that choice.

**Sources checked:** the vision (principle 8, repeatability and cost control) and CLAUDE.md §3
(Taktus proposes a change when a cheaper, more reproducible method would do the same job) point
to the rule, but say that the change is proposed, not made; ADR-0014 and ADR-0018 bound what an
`exact` step may use, not which method a `sourced` step takes; the anchor pages place the
choice with the owner (M3.13 here, the default's M3.13 too); the register's precedent DEC-0037
asked the same kind of question for P-03 and was answered by the owner, which confirms the
question is his rather than answering this one.

## 3. What you must decide

Does P-01 reconcile the roadmap with the issues by a rule over the issue numbers the roadmap's
items name, or by a language model that matches the items' words to the issues?

## 4. What you need to know to decide

- **A rule** gives the same report for the same roadmap and issues on every run. Its verdict
  can be classed `exact`: nothing a model produced is in it. Its condition is that each roadmap
  item names its issues by number, and that a new issue in a version is added to an item.
- **A language model** reads the items and the issue titles and judges which belongs to which.
  It needs no numbers in the roadmap. Its answer can differ between two daily runs with nothing
  changed, so the report would change by itself. Its answer is `sourced`: it leaves the step
  only through a check, and a check can confirm the shape of the answer — that every number it
  names is an open issue — but not that the match is right.
- **What the numbers cost.** Every item names its issues, as `(#85)`; an item delivered before
  the backlog existed names its pull requests. A new issue in a version is a line edit in the
  roadmap, which P-01's report asks for when it is missing. The roadmap is touched by few pull
  requests; it does not become a file every pull request rewrites.
- **What is hard to change afterwards.** Neither option is. The numbers in the roadmap are
  useful to a reader either way.

## 5. Options

### Option A — a rule over the issue numbers in the roadmap (recommended)

- **Meaning:** the reconciliation is a `rule` step classed `exact`, as this pull request builds
  it. The roadmap's items name their issues, and the process page says so.
- **Consequence:** the report changes only when the roadmap or the issues change. Its findings
  are facts a person can check in the two texts. A new issue in a version needs its number in
  the roadmap, or the report names it.
- **Effort:** none beyond this pull request.
- **Reversibility:** cheap: the step's method is one entry in the bundle.
- **Why recommended:** the same job, done reproducibly and without a model's cost, which is what
  CLAUDE.md §3 asks a method choice to prefer; the condition it needs is a few numbers in an
  existing list.

### Option B — a language model, as the blueprint first described

- **Meaning:** the reconciliation is an `llm` step classed `sourced`. Its answer is a list of
  item-to-issue matches, checked for shape before it leaves; a rule turns it into the report.
  The numbers in the roadmap stay as hints for the model and for readers.
- **Consequence:** the roadmap needs no maintenance of numbers. The report can differ between
  two runs on the same state, and a wrong match is not caught by the check. Each daily run
  spends model tokens.
- **Effort:** about half a day: the model step, its check, its prompt and its test with the
  fake model.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing. The provisional answer is Option A, and P-01 runs with it. If the answer is Option B,
the step `reconcile` becomes a model step with a check, and the bundle's version rises.

## 7. How to answer

"DEC-0080: Option A." or "DEC-0080: Option B."
