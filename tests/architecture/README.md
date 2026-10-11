# Architecture tests

The adapter obligation, the component boundaries and the ban on product names in the core, as
tests (ADR-0003, ADR-0016). `import-linter` (`.importlinter`) holds the import graph; the tests
here hold what it cannot see: no product name anywhere in `components/`, `ports/`, `shared/` or
`wire/`, not even in a comment; no direct reading of the clock, minting of an identifier or
drawing of randomness — only through `ports/clock.py`; no import in the core outside the standard
library, pydantic and `taktus`; every domain model frozen and closed; `workers/` importing nothing
from the control plane; every documented component present as a package; no cluster client
outside the cluster execution adapter.

`test_no_figure_names_a_person.py` holds principle 14 in the data model (ADR-0015, UC-13.5,
NTC-0169): no value type of the core and no table holds a quantity beside a field that names a
person. A record of one act and a read of one's own are the two exceptions, each listed with its
reason or the test that proves it.
