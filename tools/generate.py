"""`make generate`: regenerate what is generated. Runs in the project environment.

One thing is generated today: `api/openapi.yaml`, the OpenAPI 3.1 document of Taktus' own REST
interface, from the FastAPI application under `src/taktus/adapters/driving/rest` — built at
the root; the path prefix an instance is served under is a server variable of the document.
Never edited by hand: `tests/adapters/rest/test_openapi.py` fails when the file differs from
what this script writes.

The shared kernel's Python types under src/taktus/shared/ are a hand-written binding checked
against the schemas by tests/contract, not generated (docs/architecture/project-structure.md
§4 says why).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = ROOT / "api" / "openapi.yaml"


def openapi_document() -> str:
    from taktus.adapters.driving.rest import build_app

    # The document depends on the routes alone; no service is called to produce it.
    app = build_app(_NoServices(), prefix="/")  # type: ignore[arg-type]
    return yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True, width=100)


class _NoServices:
    """Stands in for `RestServices` while the document is produced; nothing is called."""

    roles: tuple[str, ...] = ()
    tenants: tuple[str, ...] = ("default",)
    leading = False


def main() -> int:
    document = openapi_document()
    OPENAPI.parent.mkdir(parents=True, exist_ok=True)
    changed = not OPENAPI.is_file() or OPENAPI.read_text(encoding="utf-8") != document
    OPENAPI.write_text(document, encoding="utf-8")
    print(f"generate: {OPENAPI.relative_to(ROOT)} {'written' if changed else 'unchanged'}")
    print("  shared kernel: a checked binding under src/taktus/shared/ (tests/contract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
