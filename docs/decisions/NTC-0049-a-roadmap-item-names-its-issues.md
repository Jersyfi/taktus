# NTC-0049 — A roadmap item names its issues

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** [#127](https://github.com/Jersyfi/taktus/pull/127)
**How it follows:** DEC-0051 says an issue's milestone follows the roadmap, and principle 8 asks that what is checked be repeatable; a statement "the issue follows the roadmap" can only be checked repeatably when the roadmap says which issues carry an item, so every item names them. Principle 1 forbids a parallel register, so the link is written into the roadmap's existing lists, not kept in a second file. Between a link a rule reads and a match a model guesses, the stricter in substance is the link; adding numbers to lines that already exist is the option with less ceremony.

## 1. What was decided

Every item of a milestone in `docs/roadmap.md` names the issues that carry it, as `#N`. An item
delivered before the backlog existed names the pull requests that delivered it. The roadmap
says so above its milestones, and `docs/process/README.md` says so under *The backlog*.

This pull request wrote the numbers in. Where an open issue in a milestone matched no item of
that milestone, an item was added for it, in the milestone the issue already had (M1.7): in
`0.1.0`, the cluster execution adapter, the chart and the image build, and the installed
instance with its backup; in `0.2.0`, the identity component, the refusal of credentials for an
instance's own infrastructure, and P-01 to P-03 running on Taktus's own instance; in `0.5.0`,
principle 14 enforced in the data model. Each of these was already placed by its issue's
milestone or by the roadmap's own prose; the list now says it too. The 24 items of `0.3.0` to
`1.0.0` that no issue carries were left without a number: that is what P-01 reports, and
creating their issues is a task of its own.

## 2. The evidence

- Before: P-01's rule found 54 items naming no issue and 34 open issues the roadmap did not
  place, on the roadmap and the open issues of 2026-10-09. After: 24 items and no issue.
- The 0.1.0 prose already said that `mlbench` is a task of `0.4.0` and that the identity
  component, time triggers, event reactions and governance are tasks of `0.2.0`; the lists now
  carry the same placements as numbers.
- `tests/components/run/test_roadmap_rule.py` reads a roadmap in this shape, and the prose after
  each completion criterion, which names pull requests freely, is not read.

## 3. What was considered

- **The issue names its roadmap item**, in its section "Source". Rejected: an item's text
  changes when the roadmap is edited, and every issue would then have to be edited to follow;
  the roadmap is the stated intent and is the one place that lists what a milestone contains.
- **A separate file mapping items to issues.** Rejected: a parallel register, which principle 1
  forbids, and a second place to keep current.
- **No link, a model matches the words.** That is DEC-0080's Option B. The numbers stand under
  either answer: they help a reader, and a model's match too.

## 4. Which entry permits it

None does. M1.7 lets the session decide which feature lands in which milestone, which covers
the items added, but no entry says how the roadmap is linked to the backlog. The decision
follows DEC-0051, principle 8 and principle 1, as stated above, and is therefore an `unlisted`
notice under M2.6.

## 5. The entry it proposes

**M1.12** — **how the roadmap names the issues that carry its items**: the form of the link
between a roadmap item and its issues or pull requests, and adding an item to a milestone's
list for an issue the milestone already holds. Mode 1, visible in `docs/roadmap.md`; adding a
feature the owner has not accepted stays M3.2.
