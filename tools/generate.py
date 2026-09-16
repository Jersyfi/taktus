# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""`make generate`: regenerate what is generated from contracts/.

Nothing yet. The shared kernel's Python types under src/taktus/shared/ are a hand-written
binding checked against the schemas by tests/contract, not generated
(docs/architecture/project-structure.md §4 says why). `api/openapi.yaml` is generated from the
REST interface once that exists. This script exists so that the target says so instead of
failing with a missing file, and so that generation has its one place when it arrives.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("generate: nothing is generated yet")
    print("  shared kernel: a checked binding under src/taktus/shared/ (tests/contract)")
    print("  api/openapi.yaml: arrives with the REST interface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
