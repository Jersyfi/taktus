# DEC-0182 — ADR-0065 said every wiki checks a write on its side

**Category:** DEFECT
**Raised in:** the pull request that corrects ADR-0065, after #197 (pull request #262)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

ADR-0065, *Where this promise ends*, bounded the directory connector's check-then-replace to one
file write and said that "a knowledge system with a server checks on its side". The first such
system connected, the wiki of #197, offers no conditional write. Its connector reads the page,
compares the digest and writes, in two moves, as the directory connector does; its README says
so, and NTC-0193 records it. The ADR promised more than the product keeps.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4, an ADR amendment where an ADR is
involved.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The bullet now says that a server checks on its side only where it offers a conditional write,
  and that the wiki connector has two moves too, its window one request long.
- Nothing the software does changes; the connector already behaves as its README says.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0182" in an issue.

## Outcome

**Corrected:** 2026-10-12
**What was wrong:** ADR-0065 said that every knowledge system with a server checks a write that expects a digest on its side.
**Why it was wrong:** the ADR was written before a server-backed knowledge system was connected; the first one has no conditional write.
**What it now says:** a server checks on its side only where it offers a conditional write; the wiki connector reads, compares and writes in two moves, its window one request long.
**What changed in substance:** nothing; the bound the connector keeps is now the one the ADR states.
**Recorded in:** the pull request that corrects ADR-0065
