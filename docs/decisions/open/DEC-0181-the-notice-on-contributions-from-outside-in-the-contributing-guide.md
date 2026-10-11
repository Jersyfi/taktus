# DEC-0181 — The notice on contributions from outside in the contributing guide

**Category:** NON-BLOCKING
**Mode entry:** M3.7
**Raised in:** [#263](https://github.com/Jersyfi/taktus/pull/263), which builds issue #245 for UC-1.9
**Issue:** [#261](https://github.com/Jersyfi/taktus/issues/261)
**Needed by:** before the triage is switched on for this repository
**Provisional answer:** none is published. `CONTRIBUTING.md` stays as it is, and the triage stays switched off on the instance (`TAKTUS_TRIAGE` unset) until you answer: nobody's data is processed by it before the notice says so.

## 1. What this is about

Since DEC-0175, an issue or a pull request opened in this repository by a person Taktus does
not know starts a triage process for you (UC-1.9). The process reads public data of that
person: what they wrote, and the account the repository host shows beside it. Principle 11
asks for a stated purpose and a notice before a person's data is processed. UC-1.9 §2 requires
the notice in the contributing guide, and says its wording is yours.

The session drafted it. This request puts the draft to you.

## 2. Why you are being asked

Entry M3.7 of `docs/decisions/anchors.taktus.md`: "Anything published under the project's
name". The contributing guide is published under the project's name, and the notice speaks for
it.

**Sources checked:** the vision (`docs/vision/`) — principle 11 (European values: a stated
basis and a notice) and principle 14 (no assessment of individuals) — says what the notice
must cover, not its words. The anchor pages: both keep what is published under the project's
name with you (M3.7). UC-1.9 §2 and
§3 place the wording with you. DEC-0175 says the session drafts it. ADR-0012 and DEC-0044 keep
outside code from being merged, which the notice repeats. No earlier decision words a notice.

## 3. What you must decide

Whether the notice below goes into `CONTRIBUTING.md` as written, in your own words, or not at
all.

## 4. What you need to know to decide

**The draft**, as it would stand under a heading *Issues and pull requests from people we do
not know*:

> This repository is public. When you open an issue or a pull request here and the project
> does not know you, the software developed here, Taktus, handles it for the maintainer.
>
> It reads what the repository host shows anyone about your issue or pull request: its title,
> its text, its number, and the account that opened it. It uses them for one purpose: to tell
> whether it reports a defect, proposes a feature or is spam, to put a defect or a feature to
> the maintainer, and to keep it open or close it with the reason. Spam is closed without
> asking anyone; if that was a mistake, a maintainer reopens it.
>
> Taktus never acts as you. It gives you no right, does not block you, does not merge your pull
> request, and keeps no profile of you and no count of what you contributed. Its log records
> what it did to your issue or pull request, never your account. Its record of a run keeps the
> issue or pull request as it read it, account included, for as long as run records are kept.
>
> Pull requests are not merged until a licence is chosen (see above). Questions and objections
> are welcome as an issue.

**What the draft does not say.** It names no legal basis and no contact address: both are
yours to state, and a basis stated wrongly is worse than none. It does not name the
repository host.

**What happens on each answer.** The text goes into `CONTRIBUTING.md` in a change of its own,
and you switch the triage on for the repository on the instance (`TAKTUS_TRIAGE`).

## 5. Options

### Option A — publish the draft as written (recommended)

- **Meaning:** the notice above goes into `CONTRIBUTING.md`; the triage may then be switched on.
- **Consequence:** outside contributors read what happens to their issue before it happens.
- **Effort:** a short change.
- **Reversibility:** cheap: a later wording replaces it.
- **Why recommended:** it states purpose, scope and limits, says what is kept and what is
  not, and claims nothing the software does not do.

### Option B — publish it in your own wording

- **Meaning:** you give the text, or the changes to the draft; that text goes in.
- **Consequence:** as A, in your words.
- **Effort:** yours, then a short change.
- **Reversibility:** cheap.

### Option C — no notice; the triage stays off for this repository

- **Meaning:** nothing is published, and outside contributions stay as they are today: offered
  the link, otherwise untouched.
- **Consequence:** UC-1.9 is built and tested but does not run here.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing in the repository. Switching the triage on for this repository waits for the answer.

## 7. How to answer

"DEC-0181: Option A.", "DEC-0181: Option B." with your text, or "DEC-0181: Option C." — in issue
[#261](https://github.com/Jersyfi/taktus/issues/261). A free-text answer is read back as an interpretation and confirmed
before it is acted on.
