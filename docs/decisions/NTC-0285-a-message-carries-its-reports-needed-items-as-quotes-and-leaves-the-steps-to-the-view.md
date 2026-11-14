# NTC-0285 — A message carries its report's needed items as quotes and leaves the steps to the view

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-14
**Raised in:** branch `area/reports` (package F, concept mode, DEC-0239)
**How it follows:** DEC-0239 point 2 requires that every message leads with one line, says what
is needed in at most a few lines and links to the full record. UC-6.11 §2 requires that the
repository text, the message and the view of a decision request, a need and a date carry the
same identifier, the same needed items and the same date. It requires no more of the message.
The rule below keeps exactly that and drops the rest. Of two readings consistent with both
sources, the one with the shorter message is taken.

## 1. What was decided

A message is the report's short form (ADR-0316 §2).

- A decision request, a need and a date carry each needed item, as a quote of one line, and a
  decision request each option, cut to a few words.
- Every message carries the date. It carries the identifier in the link to the report's page,
  or on its own where no page is configured.
- The steps, what stands still and a failure's needed items stay in the repository text and
  the view. The message does not repeat them.
- A needed item is the record's text. Where the record is English and the phrasebook is not,
  the quote is English. It is set apart as a quote, and every other line is in the
  phrasebook's language.

`tests/components/reporting/test_owner_channel.py` now holds the message to the needed items,
the options, the identifier and the date. It holds the steps and what stands still to the
repository text and the view.

## 2. The evidence

- The message of 2026-11-14 was about 1,300 characters, most of it steps and what stands still.
  The owner could not act on it (DEC-0239).
- UC-6.11 §2, first bullet: "the same identifier, the same needed items and the same date".
- `tests/components/reporting/test_message_form.py` renders every kind and finds each message
  within 400 characters without its addresses, plus 120 for each quoted item or list line
  after the first.

## 3. What was considered

- **Carry the steps too, shortened.** Rejected. A step cut to one line loses its point, and the
  view holds it whole one click away.
- **Translate the needed items.** Rejected. The record is English by rule (CLAUDE.md §9), and a
  second text per language could disagree with the record.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

M1.28, a mode-1 entry: what a message carries beyond what a use case requires of it is the
session's, as long as the full record is one link away.
