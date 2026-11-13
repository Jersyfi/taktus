# DEC-0236 — The final round before 1.0, in concept mode

**Category:** NON-BLOCKING
**Mode entry:** M3.6 and M3.15 (how work lands and what holds a release back), DEC-0222 (concept mode)
**Raised in:** the session of 2026-11-13, by the owner's message in conversation
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-13
**Written after the answer:** the owner stated it in conversation on 2026-11-13; left out of the acceptance rate (DEC-0042).

## 1. What this is about

After release 1.0 (DEC-0228, #681) the owner asks for a final round, so that everything of the
milestones up to `1.0.0` and `introduction` is built, and nothing but `2.0.0` stays open.

## 2. Why you are being asked

How work lands, what a release holds and when it is rolled out are the owner's (M3.6, M3.15).

**Sources checked:** DEC-0222 (concept mode), DEC-0225, DEC-0226, DEC-0228 (release 1.0).

## 3. What you must decide

The scope of the round, how it lands and what the session may do at its end.

## 4. What you need to know to decide

The open issues and the use cases not yet `verified` say what remains; what only a person, the
live instance or time can give is stated, not faked (DEC-0228).

## 5. Options

### Option A — the round as the owner described it (recommended)

### Option B — the remaining issues one by one

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-13
**Answer:** Option A, in the owner's words: "Mache eine Finale Runde, dass alles für 1.0
vorbereitet ist. [...] Nur 2.0 ist für mich außen vor und der rest sollte vollständig umgesetzt
sein [...] im Konzeptmodus mit einem PR mit nur einem finalen CI run [...] die Lizenz kannst du
erstmal außenvor machen, da ich das kurz vor dem 1.0 Release selbst machen werde und wir solange
nicht in die 1.0 gehen. [...] Mergen ist dir am Ende erlaubt als auch die fertige Version als
Release zu erstellen und dann auszurollen."
**Reasoning given:** everything for 1.0 prepared; the licence follows from the owner before 1.0.0.
**What it changes:**

1. **The round is built in concept mode** on `concept/final-1-0` and lands in one pull request
   with one CI run.
2. **In scope:** every open issue and use case outside milestone `2.0.0`. The licence (DEC-0044)
   stays out; `1.0.0` is not tagged before it is answered.
3. **The session may merge the pull request when it is green, create the release and roll it
   out** on the project's own instance. The release's name is DEC-0237's.

**Recorded in:** this pull request
