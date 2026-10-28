#!/usr/bin/env python3
"""The connectors of a one-server install, from the operator's list (deploy/docker/README.md).

Compose cannot repeat a service for every entry of a list. This program reads the operator's
`connectors.json` beside it and writes `compose.connectors.yml`, which `make up` and `make
start` lay over `compose.yml`. Both files are the operator's, and git ignores them. The entry is
the chart's `connectors.others` (deploy/k8s/README.md §2), checked by the same rules:

    {"connectors": [
      {"name": "payments", "capability": "payments.subscriptions",
       "module": "taktus.adapters.driven.connectors.stripe", "port": 9111,
       "credentials": [{"name": "PAYMENTS_TOKEN", "file": "payments_token"}]}
    ]}

Each connector becomes the service `connector-<name>`: from the control plane's image running
its module, or from an image of its own. It publishes no port; the `taktus` service reaches it,
and `TAKTUS_CONNECTORS` on that service names it by its capability. A credential is a file the
operator writes under `secrets/`, mounted as a compose secret, its path in
`TAKTUS_CREDENTIAL_<NAME>_FILE` (CREDENTIALS.md). Its value never passes through this program.

Without `connectors.json` nothing is configured, and a `compose.connectors.yml` this program
wrote before is removed: it is its own output. Standard library only, as `make up` needs only
python3. Exit code 0 when written or nothing is configured, 2 when the list is refused.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LIST = HERE / "connectors.json"
OUTPUT = HERE / "compose.connectors.yml"
SETTINGS = HERE / "taktus.env"
IMAGE = "taktus:local"
"""The control plane's image as `compose.yml` builds it."""
MARK = "taktus.connectors"
"""What the written file carries, so that only a file of this program's is ever removed."""

NAME = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
LABEL = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
PARAMETER = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")
FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VERSION = re.compile(r"^v?[0-9]+(\.[0-9]+)*([-+._][0-9A-Za-z.-]+)?$")
BUILT_IN = ("repository", "chat")


class Refused(ValueError):
    """The list cannot be deployed as it is written."""


def _check(entries: list[Any]) -> None:
    names: list[str] = list(BUILT_IN)
    labels: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise Refused("connectors: each entry is an object")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise Refused("connectors[].name is required")
        if not NAME.match(name):
            raise Refused(
                f"connectors: {name!r} is not a connector name: lowercase letters and digits, "
                "words joined by hyphens"
            )
        if len(name) > 40:
            raise Refused(f"connectors: {name!r} is longer than 40 characters")
        if name in names:
            raise Refused(f"connectors: {name!r} is named twice, or is a built-in connector's name")
        names.append(name)
        label = entry.get("capability")
        if not isinstance(label, str) or not label:
            raise Refused(
                f"connectors {name}: capability is required: its label in TAKTUS_CONNECTORS"
            )
        if not LABEL.match(label):
            raise Refused(
                f"connectors {name}: capability {label!r} is not a dotted lowercase label"
            )
        if label in labels:
            raise Refused(
                f"connectors {name}: capability {label!r} is another connector's label already"
            )
        labels.append(label)
        module, image = entry.get("module"), entry.get("image")
        if module and image:
            raise Refused(f"connectors {name}: give module or image, not both")
        if not (module or image):
            raise Refused(f"connectors {name}: module or image is required")
        if image:
            tag = str(image).rpartition(":")[2] if ":" in str(image).rpartition("/")[2] else ""
            if not tag:
                raise Refused(f"connectors {name}: image {image!r} names no tag; give the version")
            if not VERSION.match(tag):
                raise Refused(f"connectors {name}: image tag {tag!r} is not a version")
        port = entry.get("port")
        if port is None:
            raise Refused(f"connectors {name}: port is required")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise Refused(f"connectors {name}: port {port!r} is not a port")
        if not all(isinstance(a, str) for a in entry.get("args", [])):
            raise Refused(f"connectors {name}: args are text")
        seen: list[str] = []
        for credential in entry.get("credentials", []):
            parameter = credential.get("name") if isinstance(credential, dict) else None
            if not isinstance(parameter, str) or not parameter:
                raise Refused(f"connectors {name}: credentials[].name is required")
            if not PARAMETER.match(parameter):
                raise Refused(
                    f"connectors {name}: credential {parameter!r} is not a parameter name such "
                    "as PAYMENTS_TOKEN"
                )
            if parameter in seen:
                raise Refused(f"connectors {name}: credential {parameter} is named twice")
            seen.append(parameter)
            file = credential.get("file")
            if not isinstance(file, str) or not FILE.match(file):
                raise Refused(
                    f"connectors {name}: credential {parameter} needs file: a file name under "
                    "secrets/"
                )


def _secret(name: str, parameter: str) -> str:
    return f"connector_{name.replace('-', '_')}_{parameter.lower()}"


def compose(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The compose file that adds the connectors and tells the `taktus` service where they are."""
    _check(entries)
    services: dict[str, Any] = {}
    secrets: dict[str, Any] = {}
    addresses: list[str] = []
    for entry in entries:
        name, port = entry["name"], entry["port"]
        service = f"connector-{name}"
        args = list(entry.get("args", []))
        definition: dict[str, Any] = {}
        if entry.get("module"):
            definition["image"] = IMAGE
            definition["command"] = [
                "python",
                "-m",
                entry["module"],
                "--host",
                "0.0.0.0",  # noqa: S104 — inside its container, reached by the compose network
                "--port",
                str(port),
                *args,
            ]
        else:
            definition["image"] = entry["image"]
            if entry.get("command"):
                definition["entrypoint"] = list(entry["command"])
            if args:
                definition["command"] = args
        environment: dict[str, str] = {}
        mounted: list[str] = []
        for credential in entry.get("credentials", []):
            secret = _secret(name, credential["name"])
            secrets[secret] = {"file": f"./secrets/{credential['file']}"}
            mounted.append(secret)
            environment[f"TAKTUS_CREDENTIAL_{credential['name']}_FILE"] = f"/run/secrets/{secret}"
        if environment:
            definition["environment"] = environment
        if mounted:
            definition["secrets"] = mounted
        health = entry.get("healthPath", "/health")
        if health:
            probe = (
                "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen("
                f"'http://127.0.0.1:{port}{health}', timeout=3).status == 200 else 1)"
            )
            definition["healthcheck"] = {
                "test": ["CMD", "python3", "-c", probe],
                "interval": "5s",
                "timeout": "5s",
                "retries": 30,
                "start_period": "10s",
            }
        definition["restart"] = "unless-stopped"
        services[service] = definition
        addresses.append(f"{entry['capability']}=http://{service}:{port}/mcp")
    services["taktus"] = {
        "environment": {"TAKTUS_CONNECTORS": ",".join(addresses)},
        "depends_on": {
            f"connector-{e['name']}": {
                "condition": "service_healthy"
                if e.get("healthPath", "/health")
                else "service_started"
            }
            for e in entries
        },
    }
    document: dict[str, Any] = {"x-written-by": MARK, "services": services}
    if secrets:
        document["secrets"] = secrets
    return document


def _set_in_settings(settings: Path) -> bool:
    if not settings.is_file():
        return False
    for line in settings.read_text(encoding="utf-8").splitlines():
        if line.strip().partition("=")[0].strip() == "TAKTUS_CONNECTORS":
            return True
    return False


def write(listed: Path, output: Path, settings: Path) -> str:
    """Write the compose file for the list, or remove a stale one when there is no list."""
    if not listed.is_file():
        if output.is_file() and MARK in output.read_text(encoding="utf-8"):
            output.unlink()
            return f"connectors: none configured; removed {output.name}"
        return "connectors: none configured"
    if _set_in_settings(settings):
        raise Refused(
            f"{settings.name} sets TAKTUS_CONNECTORS, and {listed.name} sets it too: name the "
            f"connectors in {listed.name} alone"
        )
    try:
        document = json.loads(listed.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Refused(f"{listed.name} is not JSON: {error}") from error
    entries = document.get("connectors") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise Refused(f"{listed.name}: `connectors` is a list")
    output.write_text(json.dumps(compose(entries), indent=2) + "\n", encoding="utf-8")
    return f"connectors: wrote {output.name} with {len(entries)} connector(s)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", type=Path, default=LIST, help="the operator's connectors.json")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="the compose file written")
    parser.add_argument("--settings", type=Path, default=SETTINGS, help="the operator's taktus.env")
    args = parser.parse_args(argv)
    try:
        print(write(args.list, args.output, args.settings))
    except Refused as error:
        print(f"connectors: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
