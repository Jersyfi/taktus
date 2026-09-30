<!--
The order of the sections is fixed (ADR-0017 §7). Keep the headings as they are.

Write for a reader who has not opened the diff, the session or any ADR. Every section below
must make sense to them on its own: name the problem, not the file; say what changed, not
where; give the reason, not the history. CI fails a description without the first four
sections, with one of them empty, or with them out of order (tools/check_decisions.py).
-->

## What this is about

<!-- The problem or the goal, in plain sentences. What was wrong, missing or wanted, and for
whom. A reader who knows Taktus only from the README can follow it. -->

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

## What was done

<!-- What is different after this change, as behaviour and as documents, not as a file list.
Records it creates or corrects, by ID. -->

## Why this way

<!-- The reason for this shape over the alternatives that were considered, and what it costs. -->

## What to check

<!-- What the reviewer should look at, in order of risk: the place a mistake would hurt most,
the claim that is hardest to verify, the thing the gates cannot see. How CLAUDE.md §11 is met. -->

## Notes

<!-- Information for the owner. Statements, never questions. Delete the section if empty. -->

## Needed from the owner

<!--
The last section, always: the output of `make status`, verbatim — every open needs request and
decision request, the most urgent first, with its date and issue, generated from the register
of this branch. CI fails when this differs from what the register generates (ADR-0028,
DEC-0026). The list is carried here and nowhere else: never paste it into docs/status.md.

The pull request targets main. A change that needs another unmerged change waits for it to
merge, then rebases on main; CI fails a pull request based on any other branch (DEC-0026).
-->
