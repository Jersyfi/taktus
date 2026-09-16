"""The console script `taktusctl`: the command-line adapter, wired for a developer's machine."""

from __future__ import annotations

from taktus.adapters.driving.cli.main import app
from taktus.composition.local import LocalWiring


def main() -> None:
    app(obj=LocalWiring())


if __name__ == "__main__":
    main()
