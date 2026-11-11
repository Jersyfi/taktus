# DEC-0234 — The user and developer documentation, written in English and hosted on web hosting

**Category:** NON-BLOCKING
**Mode entry:** M3.7 (what is published under the project's name), M3.15 (what a release holds)
**Raised in:** the session that builds release 1.0 (DEC-0228), by the owner's message of 2026-11-12
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-12
**Written after the answer:** the owner stated it in conversation on 2026-11-12; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The release closes with documentation for the people who use Taktus and the people who build on
it.

## 2. Why you are being asked

What a release holds and what is published under the project's name are the owner's (M3.7, M3.15).

**Sources checked:** UC-13.6 and ADR-0065 (the guides rendered from the repository), NEED-0021
(a wiki for the guides, never provided), DEC-0228 (release 1.0).

## 3. What you must decide

What documentation the release carries, how it is written and where it is hosted.

## 4. What you need to know to decide

Two guides exist, rendered from the repository by `taktusctl guides`: administration and use. No
guide exists for a developer who builds an adapter or a process, which the 1.0.0 condition "a
stranger builds an adapter without asking" needs.

## 5. Options

### Option A — the documentation as the owner described it (recommended)

### Option B — the guides as they are

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-12
**Answer:** Option A, in the owner's words: "Am Ende musst du eine Anwender-/Entwickler-
dokumentation verfasse auf englisch. Für Dokumentationen ist mir wichtig, dass wir nur die
notwendigen Informationen so viel wie nötig und so wenig wie möglich auf den punkt gebracht
runter schreiben. Überlege dir welches Tool hier am Besten wäre. Am liebsten würde ich es wenn
möglich bei IONOS im Webhosting hosten."
**Reasoning given:** none beyond the request.
**What it changes:**

1. **Release 1.0 carries user and developer documentation in English.** It is a third guide,
   *Developing*, beside *Administering* and *Using*. All three are rendered from the repository by
   the existing guides manifest.
2. **The documentation states only what a reader needs:** as much as necessary, as little as
   possible.
3. **The tool is the session's choice** (NTC-0272).
4. **It is hosted on the owner's web hosting at IONOS.** The access is NEED-0043. Whether it is
   public is DEC-0235, because publishing under the project's name is M3.7.

**Recorded in:** this pull request
