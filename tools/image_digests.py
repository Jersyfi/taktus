"""Record the digest of every image one run of the image workflow published (ADR-0173 §6).

    python3 tools/image_digests.py --in DIR --out DIR

Each build of `.github/workflows/images.yml` writes one file into DIR: one JSON object with the
image's `name` (`taktus`, `taktus-backup`, `taktus-worker-<x>`, `taktus-connector-<x>`), its
`repository`, the `tag` it was published under and its `digest`, `sha256:` and 64 hexadecimal
characters. The tool writes two files into the output directory:

- `images.json`: every image, in the order of its name, with its reference by digest.
- `digests.values.yaml`: the chart's values (`deploy/k8s/chart`) that pin every image the chart
  derives from the release — `image.digest`, `backup.image.digest` and
  `connectors.digests.<name>` — for `helm upgrade -f`. A worker's image is named by the
  operator in `execution.image` or `execution.workers`; its reference by digest is listed as a
  comment to copy from.

It refuses, writing nothing, a file that is not such an object, a digest of another form, two
files for one image, and images of one run under different tags. Standard library only, so
that the workflow runs it with the runner's Python.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
NAME = re.compile(r"^taktus(-[a-z0-9]+)*$")
FIELDS = ("name", "repository", "tag", "digest")
CONNECTOR = "taktus-connector-"
WORKER = "taktus-worker-"


class Refused(Exception):
    """An input the record cannot be written from."""


def read(directory: Path) -> list[dict[str, str]]:
    images: dict[str, dict[str, str]] = {}
    for path in sorted(p for p in directory.iterdir() if p.is_file()):
        try:
            entry: Any = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise Refused(f"{path.name}: not JSON ({error})") from error
        if not isinstance(entry, dict) or set(entry) != set(FIELDS):
            raise Refused(f"{path.name}: an object with exactly {', '.join(FIELDS)}")
        if not all(isinstance(entry[f], str) and entry[f] for f in FIELDS):
            raise Refused(f"{path.name}: every field is a string that is not empty")
        if not NAME.fullmatch(entry["name"]):
            raise Refused(f"{path.name}: {entry['name']!r} is no image name of this project")
        if not DIGEST.fullmatch(entry["digest"]):
            raise Refused(f"{path.name}: {entry['digest']!r} is not sha256:<64 hex>")
        if entry["name"] in images:
            raise Refused(f"{path.name}: {entry['name']} is recorded twice")
        images[entry["name"]] = {f: entry[f] for f in FIELDS}
    if not images:
        raise Refused(f"{directory}: no image recorded")
    tags = {image["tag"] for image in images.values()}
    if len(tags) != 1:
        raise Refused(f"one run publishes one tag, these carry {', '.join(sorted(tags))}")
    return [images[name] for name in sorted(images)]


def reference(image: dict[str, str]) -> str:
    return f"{image['repository']}:{image['tag']}@{image['digest']}"


def values(images: list[dict[str, str]]) -> str:
    by_name = {image["name"]: image for image in images}
    tag = images[0]["tag"]
    lines = [
        "# The chart's values that pin the images of one run of .github/workflows/images.yml",
        "# by digest (ADR-0173 §7), written by tools/image_digests.py. Pass with `helm -f`.",
    ]
    if "taktus" in by_name:
        lines += ["image:", f'  tag: "{tag}"', f'  digest: "{by_name["taktus"]["digest"]}"']
    if "taktus-backup" in by_name:
        lines += ["backup:", "  image:", f'    digest: "{by_name["taktus-backup"]["digest"]}"']
    connectors = [i for i in images if i["name"].startswith(CONNECTOR)]
    if connectors:
        lines += ["connectors:", "  digests:"]
        lines += [f'    {i["name"][len(CONNECTOR) :]}: "{i["digest"]}"' for i in connectors]
    workers = [i for i in images if i["name"].startswith(WORKER)]
    if workers:
        lines.append("# The workers' images, for execution.image or execution.workers[].image:")
        lines += [f"#   {i['name']}: {reference(i)}" for i in workers]
    return "\n".join(lines) + "\n"


def record(source: Path, target: Path) -> None:
    images = read(source)
    listed = [{**image, "reference": reference(image)} for image in images]
    target.mkdir(parents=True, exist_ok=True)
    (target / "images.json").write_text(json.dumps(listed, indent=2) + "\n", encoding="utf-8")
    (target / "digests.values.yaml").write_text(values(images), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--in", dest="source", type=Path, required=True)
    parser.add_argument("--out", dest="target", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        record(arguments.source, arguments.target)
    except Refused as refused:
        print(f"image_digests: {refused}; nothing written", file=sys.stderr)
        return 1
    print((arguments.target / "digests.values.yaml").read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
