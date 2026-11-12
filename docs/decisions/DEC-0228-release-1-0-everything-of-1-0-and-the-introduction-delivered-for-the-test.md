# DEC-0228 — Release 1.0: everything of 1.0 and the introduction delivered for the test

**Category:** NON-BLOCKING
**Mode entry:** M3.6 and M3.15 (how work lands and what holds a release back), DEC-0222 (concept mode)
**Raised in:** the session of 2026-11-07, by the owner's message in conversation
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-07
**Written after the answer:** the owner stated it in conversation on 2026-11-07; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The first customer is to receive a version to test. The owner asks for everything promised to
the customer, and everything of the milestones `1.0.0` and `introduction`, to be built on `main`.

## 2. Why you are being asked

How work lands and what is delivered are the owner's (M3.6, M3.15).

**Sources checked:** DEC-0222 (concept mode), DEC-0225 (live tests only for what the project
uses itself), DEC-0226 (outside systems the project does not use), DEC-0227 (package E, and its
§5 on the introduction stages).

## 3. What you must decide

The scope of the package, and how it lands.

## 4. What you need to know to decide

Package E built each stage's processes against open interfaces. It named, per stage, what no
open interface serves (`blueprints/software-operations/README.md`, *State*).

## 5. Options

### Option A — the package as the owner described it (recommended)

### Option B — the issues one by one, as before

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-07
**Answer:** Option A, in the owner's words: "Schaue dir bitte an was wir dem Kunden versprochen
habe, was du dazu in dem Projekt findest als auch in den Issues (auch ohne Meilenstein) und in
der Privaten Dokumentation [...]. Wir müssen alle Anforderungen nun liefern und dafür muss der
Stand vollständig auf main umgesetzt sein. Ich möchte, dass alles von der Version 1.0 und
introduction umgesetzt wird, sodass wir einen sauberen Stand haben den wir zum Test geben
können. Bauche bitte alles gebündelt im Konzeptmodus mit einem PR am Ende [...] wenn wir
vollständig durch sind und lokal alles getestet wurde."
**Reasoning given:** a clean state that can be handed to the customer for testing.
**What it changes:**

1. **The package is built in concept mode** on `concept/release-1-0`. Its pull request is opened
   only once the whole package is built and tested locally.
2. **In scope:** every requirement promised to the customer, from the repository, the issues
   with or without a milestone, and the owner's private documentation. This includes every open
   task of the milestones `1.0.0` and `introduction`, and the remainders package E stated per
   stage. Milestone `2.0.0` stays out.
3. **The rules of DEC-0225 and DEC-0226 still hold.** A connector to a system the project does not
   use is built as product support and proven against a stand-in built from that system's
   published interface. It is never proven against an account of the project's own.
4. **What only the owner can provide is asked for up front**, with the steps to provide it.

**Recorded in:** this pull request
