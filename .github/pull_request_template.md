<!-- The order of the sections is fixed (ADR-0017 §7). Keep the headings as they are. -->

## What this delivers

<!-- Five lines at most. -->

## Decisions required

None

<!--
Either the single word "None", or one line per decision, nothing else:
- DEC-NNNN — <title> — BLOCKING — #<issue>
- DEC-NNNN — <title> — NON-BLOCKING — #<issue>
Every line needs a file under docs/decisions/open/. A BLOCKING line keeps this pull request a
draft; CI fails otherwise. Test the question against docs/decisions/anchors.taktus.md first:
only an entry of mode 3 or 4 justifies a request. A mode-2 decision is a notice record
(docs/decisions/NTC-NNNN-<slug>.md), named under "Notes".
-->

## Notes

<!-- Information for the owner. Statements, never questions. Delete the section if empty. -->

## Everything else

<!-- What a reviewer needs; how CLAUDE.md §11 is met; defects corrected (with their DEC record). -->

## Needed from the owner

<!--
The last section, always: the output of `make status`, verbatim — every open needs request and
decision request, the most urgent first, with its date and issue, generated from the register
of this branch. CI fails when this differs from what the register generates (ADR-0028,
DEC-0026). The list is carried here and nowhere else: never paste it into docs/status.md.

The pull request targets main. A change that needs another unmerged change waits for it to
merge, then rebases on main; CI fails a pull request based on any other branch (DEC-0026).
-->
