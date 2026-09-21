# NTC-0001 — Anchors split into two files with four modes

**Mode entry:** M2.1
**Kind:** restructuring
**Decided:** 2026-09-21
**Raised in:** [#14](https://github.com/Jersyfi/taktus/pull/14), which rebuilds the decision model from the owner's answers

## 1. What was decided

The page that says which questions reach the owner was one file with two lists: what the
owner decides, and what a session decides and records. It is now two files with four modes.
`docs/decisions/anchors.md` is the shipped default: the configuration a new tenant of Taktus
inherits, written as a template another organisation can adopt. `docs/decisions/anchors.taktus.md`
is the configuration of one tenant, the Taktus project itself, with the owner's own answers.
Every entry has an identifier, `M<mode>.<number>`, so that a request or a record can cite one
and a tenant can move one to another mode.

The content of the owner's answers is the owner's and was not decided here. What was decided
here is the structure: two files rather than one, entries with identifiers rather than rows
named `O1` to `O10` and `D1` to `D6`, and a history paragraph mapping the old rows to the new
entries so that the thirteen records written before this date still read.

## 2. The evidence

- The owner's answers of 2026-09-21 name four modes. The two-list page could hold answers of
  mode 1 and mode 3 only; the answers of mode 2 (decide and give notice) and mode 4 (the owner
  decides, the session supplies data) had no place in it.
- The two-list page was product and tenant configuration in one: ADR-0008 says every
  organisation defines its own anchor set, and ADR-0020 separates tenants, but the page named
  `.github/CODEOWNERS` in its second sentence. A template a tenant adopts cannot name this
  repository's owner.
- Thirteen records under `docs/decisions/` cite rows of the old page (`O7`, `D6`); the
  history paragraph of `anchors.taktus.md` maps every old row to its new entry, and every
  citation still resolves through it.

## 3. What was considered

- **One file with four modes.** Keeps one page to read, but keeps product and tenant
  configuration in one file, which is the fault named above.
- **Rewriting the thirteen existing records to the new identifiers.** A record is a record;
  rewriting what was cited at the time makes the register say something it did not say. The
  mapping lives in the new page instead.
- **Numbering the entries per tenant rather than per default.** A tenant would then have
  identifiers of its own and could not say "M3.4 is mode 1 here"; the point of the identifiers
  is that they name the same thing across tenants.

## 4. Which entry permits it

M2.1 of `anchors.taktus.md`: "Documentation restructuring without changing what the documents
say." The owner's answers are recorded, not changed; the structure around them is the
session's to choose, and no entry of mode 3 or 4 is touched — the content of the anchors
themselves came from the owner.
