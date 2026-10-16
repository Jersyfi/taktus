# Architecture decisions

Every decision with its context, the alternatives rejected and its consequences. An architectural
change arrives as an ADR, not as a pull request without context. Where code and an ADR disagree, the
ADR wins.

**Every ADR that makes a promise states where the promise ends.** A promise without a stated
boundary reads as a guarantee, and that is where the disappointments come from that a product
never recovers from: ADR-0005 said no limit is ever breached, and a currency limit could be;
ADR-0014 said `exact` is machine-checkable, and did not say that somebody has to write the check.
Both boundaries were documented somewhere other than where the promise was made. Hence the
section `## Where this promise ends`, last in the file, mandatory in every ADR whose prose
promises — `make gate-adrs` (`tools/check_adrs.py`) fails an ADR that promises without
bounding. The section states the boundary; it does not point at it.

The index is printed, not stored: `make adrs` lists every ADR with its title, its status and
what later ADRs say they extend, amend or supersede, generated from the files here. A stored
table conflicted whenever two pull requests each added an ADR (#392, DEC-0026).
