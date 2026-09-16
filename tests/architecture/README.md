# Architecture tests

The adapter obligation, the component boundaries and the ban on product names in the core, as
tests (ADR-0003, ADR-0016). `import-linter` (`.importlinter`) holds the import graph; the tests
here hold what it cannot see: no product name anywhere in `components/`, `ports/`, `shared/` or
`wire/`, not even in a comment; no direct reading of the clock, minting of an identifier or
drawing of randomness — only through `ports/clock.py`; no import in the core outside the standard
library, pydantic and `taktus`; every domain model frozen and closed; `workers/` importing nothing
from the control plane; every documented component present as a package.
