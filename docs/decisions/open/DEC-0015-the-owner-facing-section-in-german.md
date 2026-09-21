# DEC-0015 — The owner-facing section in German

**Category:** NON-BLOCKING
**Raised in:** [#22](https://github.com/Jersyfi/taktus/pull/22), which adds the needs request and the status report
**Issue:** [#17](https://github.com/Jersyfi/taktus/issues/17)
**Needed by:** 2026-10-19
**Provisional answer:** English, as the rule stands: the last section of every pull request description, *Needed from the owner*, is written in English; the pull request template and `tools/check_status.py` say so

## 1. What this is about

Every pull request now ends with a section that says what is needed from you: every open
request for something only you can provide, and every open question, each with its date. That
section is copied from the status file, and a check fails the pull request when the two differ.

Your brief that asked for this section said it should end "the German summary for the owner".
There is no German summary in this repository today: every pull request description, every
issue and every file of the decision register has been in English since the first pull request,
and the rule that says so is written down twice — in the working rules of the repository and in
the decision that shaped the pull request description. A session may not change a written rule
on the strength of a brief when the brief itself says the repository wins. So the section is in
English, and this asks you whether the part of a pull request that is addressed to you should
be in German instead.

## 2. Why you are being asked

No entry of mode 3 or 4 of `docs/decisions/anchors.taktus.md` makes the language of a pull
request description your call, and no entry of mode 1 or 2 makes it the session's: the rule
"everything in English" (CLAUDE.md §9; ADR-0017 §7) is a working rule of the repository, and
changing a working rule fits no entry. The page's own rule for that case — *Neither list* — says
the question is raised as a non-blocking request that proposes which mode it belongs in. It is
your question in substance too: the section exists for you, and how you want to be addressed is
yours to say.

## 3. What you must decide

Should the part of a pull request description that is addressed to you — the section *Needed
from the owner*, and a summary before it if you want one — be written in German, while the rest
of the repository stays in English?

## 4. What you need to know to decide

- **The section.** The last section of every pull request description. It is generated from
  the register: one line per open need and open question, with its date and its issue, the
  most urgent first. The same lines are in `docs/status.md`, the file that says where the
  project stands. A check compares the two and fails the pull request when they differ.
- **Why it is generated.** So that it cannot be forgotten, shortened or buried. The lesson of
  pull requests #1 and #10 is that a line written by hand in a description does not reach you.
- **What "German" would mean for the mechanism.** The generated lines carry the titles of the
  records, which are English, because the records are. A German section would either translate
  the titles on the fly — a second wording the check must also produce — or keep the titles in
  English inside German sentences. A German *summary* written by hand in addition would be a
  second thing that can be forgotten, which the check cannot verify for content.
- **What the rule protects.** One language means one wording per fact: the record, the issue,
  the description and the status say the same thing in the same words, and a search finds all
  of them. A second language for one section is a second wording to keep in step.
- **What the decision commits the project to.** Little that is hard to undo. The section's
  language is one setting of one tool and one line of the template. A summary in German in
  addition is a habit, not a mechanism, and would be stated as a rule in CLAUDE.md §9.

## 5. Options

### Option A — English, as the rule stands (recommended)

- **Meaning:** the section stays as it is: English, generated, checked. Nothing else changes.
- **Consequence:** one wording per fact; you read the section in the language of the record
  and the issue it points to, so nothing is lost between them.
- **Effort:** none.
- **Reversibility:** cheap; Option B or C can be adopted at any time.
- **Why recommended:** the section exists so that a fact reaches you unchanged. A translation
  is a change, and a hand-written summary is the kind of line that did not reach you before.

### Option B — The generated section in German, the records in English

- **Meaning:** the tool writes the section with German headings and sentences — "Benötigt bis",
  "offen seit" — around the English record titles; the template and the check follow. The
  rule in CLAUDE.md §9 gains the exception: the owner-facing section of a description is
  German.
- **Consequence:** you read a German frame around English titles; the status file keeps the
  English form, so the two sections are no longer the same text and the check compares
  content, not words.
- **Effort:** two hours: the tool, the template, the check, the rule.
- **Reversibility:** cheap.

### Option C — A German summary written by hand before the section, in addition

- **Meaning:** every description carries, before the generated section, a short German
  summary of what the pull request delivers and what it asks of you, written by the session.
  The generated section stays English. CLAUDE.md §9 states the habit.
- **Consequence:** you get a summary in your language; nothing checks that it is complete or
  that it says what the generated section says. It is the note that did not reach you, in
  another language.
- **Effort:** a paragraph per pull request, and none to set up.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing. The section is generated and checked in English now. If no answer arrives by
2026-10-19, Option A stands and this record is closed with it; adopting B or C later costs one
pull request and no rework.

## 7. How to answer

"DEC-0015: Option A.", "DEC-0015: Option B." or "DEC-0015: Option C." A free-text answer is
read back as an interpretation and confirmed before it is acted on.
