# DEC-0055 — Seeing Taktus at work, live

**Category:** NON-BLOCKING
**Raised in:** [#102](https://github.com/Jersyfi/taktus/pull/102), from the owner's idea of 2026-10-08 that whatever Taktus does should be seen, live, rather than read
**Issue:** [#101](https://github.com/Jersyfi/taktus/issues/101)
**Needed by:** 2026-10-31
**Provisional answer:** Option A. The requirement is in force as written in `docs/usecases/reporting/UC-6.10-what-taktus-does-is-seen-as-it-happens.md`, and binds any session that builds a view before the answer. Nothing is built for it before the web app of `0.3.0`. Marked in the use case and in the status file.

## 1. What this is about

You described an idea: everything Taktus does should be shown to a person in a form they grasp
at once. That means graphs, process diagrams and flows that are tied to the real data and move
while the work moves, not static pictures. It may be playful. The feel should be closer to a
thinking system than to a control room — meant as a metaphor, not as a picture of a brain.
Explanations of why Taktus did something may stay text.

The repository already points this way, but only in pieces:

- the plan for version `0.3.0`, named *visibility*, lists a web app with a dashboard and a
  "process diagram";
- the description of how Taktus runs its own development asks for "process diagrams with their
  data";
- the requirement for views per role says who may see which figure, but not how it is shown;
- the vision rules out one thing: Taktus is not a tool where processes are assembled by dragging
  blocks. Showing is wanted; building by drawing is not.

What is missing is a requirement that says what you said. Nothing requires that the display is
live, that it covers everything from the overview to a single result, or that it shows how each
step works. Without such a requirement, "a process diagram" can be met by a static image.

The session has written that requirement as a new use case, `UC-6.10`. In short, it requires:

1. **Four levels, each drawn from the live records**: the overview of the areas a person may look
   into; the process as a graph of its steps; one run, showing where it stands, what waits and on
   whom, and what it has cost so far; and the path from a result back to what produced it.
2. **Live**: a change in a run reaches every open display of it within 5 seconds, without
   reloading.
3. **Motion means something**: everything that moves corresponds to real work at that moment. An
   idle system looks idle.
4. **The display shows how each step works.** Steps whose result is reproducible look and move
   differently from steps run by a language model or an agent. A person's step and a waiting step
   look different again. This is what keeps the "thinking system" feel from suggesting that
   everything in Taktus is a language model. Avoiding that suggestion is the mistake the project
   is most determined not to make.
5. **Calm and accessible**: motion can be stopped, the system's reduced-motion setting is
   respected, and every display has a text equivalent with the same figures.
6. **Playful about the work, never about people**: no score, rank or badge for a named person.
7. **The rules that already hold for every view** still hold: a person sees only what they are
   entitled to see, every figure is the same as in the export, and the display is never the only
   way to act.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: *"What a use case requires"*, which
includes *"adding one, changing one, retiring one"*. This adds a use case. Under the same page's entry M3.2,
*"Accepting or rejecting a feature"*, and *"a proposal from a session, an issue or the owner's
own notes is a proposal until the owner accepts it"*, an idea you stated in conversation is a proposal until
you accept it in its worked form.

**Sources checked:** `docs/vision/` — principle 7 (transparency fitted to the role) and the
non-goal against a visual block builder say that showing serves transparency, but not that it is
live, nor what it must cover; principle 14 forbids assessing a person, which the use case applies
to playful elements. The ADRs — ADR-0029 puts every view in the component `reporting` and gives it
no figure of its own, ADR-0026 says the autonomy statement is shown wherever the process is shown,
ADR-0021 gives the record of a result's origin. None requires a live display. Both anchor pages —
M3.15 and M3.2 make this yours; M1.7 makes the milestone placement the session's once accepted.
The register — DEC-0030 is the precedent for a use case raised by a session and in force
provisionally; no record decides how Taktus is shown.

## 3. What you must decide

Whether the requirement `UC-6.10`, *what Taktus does is seen as it happens*, stands as written,
for version `0.3.0`.

## 4. What you need to know to decide

- **A use case** is one file that states a requirement: what must be achieved, how it is checked,
  and what is explicitly not required. Code is held to it by tests. Once accepted, a session may
  not soften it to make it easier to meet. A requirement is met, or its failure is argued.
- **Version `0.3.0`** is the milestone that brings the web app. Before it come `0.1.0`, which is
  nearly finished, and `0.2.0`, where Taktus maintains its own repository. Nothing of this use
  case is built before `0.3.0`, whatever the answer.
- **What it commits the project to.** The web app's first screens must be live and must cover the
  four levels. That is more work than a static diagram, and it shapes the web app from its first
  line. The control plane needs a way to send changes to a reader as they happen; today it only
  answers when asked. That way is an architecture decision, written as an ADR before its code.
- **What it leaves open.** No technology, style or colour is required. Which library draws and what
  it looks like is decided when the web app is built. The 5 seconds is the session's proposal; you
  may name another figure in your answer.
- **The vision is not changed.** The guiding image — Taktus experienced as a system one can watch
  thinking — is written into the use case as its design intent. Making it a guiding principle
  would change `docs/vision/`, which is your own question (M4.5) and a separate request. The
  session does not propose that, because principle 7 and the non-goal already give the direction
  the use case needs.
- **What becomes hard to change.** Once the web app is built around live representations, going
  back to static pages costs little. Going the other way, from static pages to live ones, means
  rebuilding the web app's data paths. That is why this is asked before `0.3.0` starts.

## 5. Options

### Option A — the requirement as written, in `0.3.0` (recommended)

- **Meaning:** `UC-6.10` stands with its four levels and every condition. The roadmap's `0.3.0`
  names it, and the backlog gains its tasks: the ADR for live changes, the shared visual
  vocabulary, and the four levels.
- **Consequence:** the web app is built live from its first screen. The "process diagram" of
  `0.3.0` is met only by a live, data-bound graph.
- **Effort:** none now. In `0.3.0`, the largest part of the web app's work — weeks of sessions,
  not days; it will be estimated when its tasks are made ready.
- **Reversibility:** cheap until `0.3.0` starts; afterwards a narrower requirement is a change of
  the use case, decided like this one.
- **Why recommended:** it is your idea in a form that can be checked, and it keeps the one risk the
  metaphor carries — that everything looks like a language model — under a condition rather than
  under good intentions.

### Option B — the process, the run and the vocabulary in `0.3.0`; overview and origin later

- **Meaning:** `UC-6.10` stands. The overview of the areas and the path of a result's origin move to
  `0.5.0`, where the work on result defects and the provenance record makes that path useful.
- **Consequence:** `0.3.0` is smaller. Until `0.5.0` a person goes into a process from a list,
  not from a live overview.
- **Effort:** none now; in `0.3.0` perhaps a third less than Option A.
- **Reversibility:** cheap: moving work between milestones is the session's (M1.7).

### Option C — no requirement now

- **Meaning:** `UC-6.10` is retired before it is built. The roadmap keeps "process diagram", and
  how Taktus is shown is decided when the web app is built.
- **Consequence:** a static diagram meets `0.3.0`. Your idea stays an intention, not a condition.
- **Effort:** none.
- **Reversibility:** cheap now; costly once a static web app exists.

## 6. What is blocked

Nothing today. The web app of `0.3.0` waits on this answer, and so do its tasks in the backlog,
which are written only once it is given. Without an answer by 2026-10-31 the provisional answer
stands: the requirement is in force as written, and changing it later costs a decision like this
one and, after `0.3.0` has started, the rework of what was built on it.

## 7. How to answer

"DEC-0055: Option A.", "DEC-0055: Option B." or "DEC-0055: Option C." in the issue. To change
the figure of 5 seconds, add it: "DEC-0055: Option A, with 2 seconds." To raise the guiding image
into the vision as well: "DEC-0055: Option A, and raise the guiding image as a vision request." A
free-text answer is read back as an interpretation and confirmed before it is acted on.

## Outcome

**Decided:** 2026-10-08
**Answer:** Option A, as the owner gave it in [#101](https://github.com/Jersyfi/taktus/issues/101#issuecomment-6068229988). UC-6.10 stands as written, with the 5 seconds, in `0.3.0`. The vision is not changed.
**Reasoning given:** none beyond the option; the recommendation's reason stands: the idea in a form that can be checked, with the risk the metaphor carries held by a condition.
**Recorded in:** [#102](https://github.com/Jersyfi/taktus/pull/102): the use case no longer says it is provisional; the roadmap's `0.3.0` names it (M1.7); the backlog gains its three tasks in milestone `0.3.0`, #103, #104 and #105.
