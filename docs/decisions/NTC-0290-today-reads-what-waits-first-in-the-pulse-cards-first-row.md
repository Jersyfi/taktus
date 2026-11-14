# NTC-0290 — Today reads what waits first, in the pulse card's first row

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-14
**Raised in:** branch `area/design` (package F, concept mode, DEC-0239)
**How it follows:** DEC-0239 item 4 asks for a start page that shows a living system first: a
pulse, a Takt. UC-13.7 §2 requires that "the start page shows what waits for the reader before
what runs". Both hold when the first thing read on the pulse card is how much waits for the
reader. Strict in substance, sparing in ceremony (CLAUDE.md §8): the use case stays as it is, and
the order inside the card follows it.

## 1. What was decided

- The pulse card is the first section of Today, after the way to a first process for a tenant
  without one (UC-10.4). Its first row begins with a tile: how many items wait for the reader,
  leading to `#/waits`. The overview's sentence, the live state and the Takt strip follow it.
- The list *Waits for you* comes directly after the glance strip, before *Now running*, *Just
  happened* and *What runs*.
- A count that could not be read is shown as a dash with the words *waits could not be read*,
  never as zero.

## 2. The evidence

- `web/src/routes/+page.svelte`: the tile `data-tile="waiting_for_you"` is the first element of
  the card; `web/src/lib/navigation.test.ts` holds its words, and `pulse.test.ts` holds that
  Today names a failed read instead of counting nothing.
- ADR-0322 §4 records the order.

## 3. What was considered

- **The pulse above the waits, the waits as a section below it.** Rejected: the first thing read
  would be what runs, which UC-13.7 §2 puts second.
- **Changing UC-13.7 §2 to allow the pulse first.** Rejected: a requirement is not adjusted to
  become meetable (CLAUDE.md §11 point 13), and it is met as it stands.
- **The waits as a card beside the pulse.** Rejected for a phone: side by side becomes one above
  the other, and the order would depend on the width.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

M1.20, widened: "The look of a representation, and the order inside a section of a page where a
use case fixes only which content comes first", so that the next such order is decided without a
notice. Until the owner accepts it, M2.6.
