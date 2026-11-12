"""The configuration of the documentation site, written from the guides' manifest (NTC-0272).

`make docs-site` first renders the guides into Markdown files with `taktusctl guides publish`.
This tool then writes what Zensical builds the site from, into the build directory:

- `mkdocs.yml`: `docs-site/mkdocs.yml` with the source and output directories and a navigation,
  one section per guide and one entry per page, in the manifest's order. A page's file is where
  the publication put it: its guide's place, one directory per level, and its title.
- `index.md`: the start page, `docs-site/index.md`.
- `taktus.css`: the brand colour of the web app's design tokens (`web/design/tokens.json`,
  ADR-0177), light and dark, resolved from its reference to a primitive.

A page the manifest names that the publication did not write fails the tool, naming it. The
manifest is the one list of pages; nothing here repeats it. Standard library and PyYAML only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
STYLESHEET = "taktus.css"


def navigation(manifest: dict[str, Any], pages: Path) -> list[dict[str, Any]]:
    """One section per guide, titled as the guide, with its pages in the manifest's order."""
    nav: list[dict[str, Any]] = [{"Start": "index.md"}]
    missing: list[str] = []
    for guide in manifest["guides"]:
        entries: list[dict[str, str]] = []
        for page in guide["pages"]:
            relative = Path(*guide["place"], page["title"] + ".md")
            if not (pages / relative).is_file():
                missing.append(f"{guide['id']}/{page['id']}: {relative}")
            entries.append({page["title"]: relative.as_posix()})
        nav.append({guide["title"]: entries})
    if missing:
        raise SystemExit("docs_site: the publication wrote no file for\n  " + "\n  ".join(missing))
    return nav


def resolve(tokens: dict[str, Any], value: str) -> str:
    """A token's value, its reference `{primitive.color.indigo.700}` followed to the literal."""
    while value.startswith("{") and value.endswith("}"):
        node: Any = tokens
        for key in value[1:-1].split("."):
            node = node[key]
        value = node["$value"]
    return value


def stylesheet(tokens: dict[str, Any]) -> str:
    """The theme's primary and accent colour, the web app's brand colour in each scheme; the
    configuration names the palette `custom`, which these rules fill."""
    light = resolve(tokens, tokens["semantic"]["light"]["text"]["brand"]["$value"])
    dark = resolve(tokens, tokens["semantic"]["dark"]["text"]["brand"]["$value"])
    return (
        "/* Written by tools/docs_site.py from web/design/tokens.json: text.brand. */\n"
        f'[data-md-color-scheme="default"][data-md-color-primary="custom"] {{\n'
        f"  --md-primary-fg-color: {light};\n"
        f"  --md-primary-fg-color--dark: {light};\n"
        f"  --md-accent-fg-color: {light};\n"
        f"  --md-typeset-a-color: {light};\n"
        "}\n"
        f'[data-md-color-scheme="slate"][data-md-color-primary="custom"] {{\n'
        f"  --md-primary-fg-color: {dark};\n"
        f"  --md-primary-fg-color--dark: {dark};\n"
        "  --md-primary-bg-color: #000000;\n"
        f"  --md-accent-fg-color: {dark};\n"
        f"  --md-typeset-a-color: {dark};\n"
        "}\n"
    )


def write(manifest_path: Path, config_path: Path, build: Path) -> Path:
    manifest = yaml.safe_load(manifest_path.read_text("utf-8"))
    pages = build / "src"
    config = yaml.safe_load(config_path.read_text("utf-8"))
    config["docs_dir"] = "src"
    config["site_dir"] = "site"
    config["nav"] = navigation(manifest, pages)
    config["extra_css"] = [STYLESHEET]
    shutil.copyfile(config_path.parent / "index.md", pages / "index.md")
    tokens = json.loads((ROOT / "web" / "design" / "tokens.json").read_text("utf-8"))
    (pages / STYLESHEET).write_text(stylesheet(tokens), "utf-8")
    out = build / "mkdocs.yml"
    out.write_text(
        "# Written by tools/docs_site.py; never edited by hand.\n"
        + yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        "utf-8",
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True, help="the guides' manifest")
    parser.add_argument(
        "--config", type=Path, required=True, help="the site's configuration, beside index.md"
    )
    parser.add_argument(
        "--build", type=Path, required=True, help="the build directory; its src/ holds the pages"
    )
    args = parser.parse_args(argv)
    out = write(args.manifest, args.config, args.build)
    print(f"docs_site: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
