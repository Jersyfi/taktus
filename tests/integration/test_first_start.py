"""The first start of a new instance, and the clock's reading (UC-10.4, ADR-0136 §6, #405).

`taktusctl first start` on a database that serves no tenant but `default` creates a tenant and
its administrator and prints the account key once; run again, it creates nothing and names the
same tenant. `taktusctl first rehearsal` reads, as JSON, that no rehearsal has run yet. The
database is the test's own, as for the tenant registry: the shared one holds other tests'
tenants.
"""

from __future__ import annotations

import json
import os
import subprocess

from .test_first_slice import PLAIN, taktusctl
from .test_tenant_registry import own_database

__all__ = ["own_database"]


def first(url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, **PLAIN, "TAKTUS_DATABASE_URL": url}
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "first", *arguments],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_the_first_start_creates_one_tenant_once_and_prints_its_key_once(
    own_database: str,
) -> None:
    made = first(own_database, "start", "--name", "The Jansens")
    assert made.returncode == 0, made.stderr
    lines = made.stdout.splitlines()
    tenant = lines[0].removeprefix("tenant ")
    assert tenant.startswith("tnt_"), made.stdout
    assert "shown once" in made.stdout and "tka_" in made.stdout
    assert "http://localhost:8080/app/" in made.stdout
    again = first(own_database, "start")
    assert again.returncode == 0, again.stderr
    assert again.stdout.splitlines()[0] == f"tenant {tenant}"
    assert "nothing was created" in again.stdout and "tka_" not in again.stdout
    read = first(own_database, "rehearsal", "--tenant", tenant)
    assert read.returncode == 0, read.stderr
    assert json.loads(read.stdout) == {
        "tenant": tenant,
        "rehearsal_started_at": None,
        "rehearsal_finished_at": None,
        "run": None,
    }
