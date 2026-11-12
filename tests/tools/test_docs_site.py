"""The documentation site (DEC-0234, NTC-0272): its navigation is the guides' manifest, its
colours are the web app's tokens, and `make docs-site` builds it into static files with search."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import docs_site  # noqa: E402 — a script under tools/, found through the line above

MANIFEST = {
    "guides": [
        {
            "id": "use",
            "title": "Using it",
            "reader": "anyone",
            "place": ["Docs", "Using"],
            "pages": [
                {"id": "b", "title": "Second by name, first in order", "parts": []},
                {"id": "a", "title": "A page", "parts": []},
            ],
        },
        {
            "id": "admin",
            "title": "Running it",
            "reader": "operators",
            "place": ["Docs", "Running"],
            "pages": [{"id": "c", "title": "Installing", "parts": []}],
        },
    ]
}


def published(build: Path, *pages: str) -> None:
    for page in pages:
        path = build / "src" / page
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# page\n", "utf-8")


def configuration(tmp_path: Path) -> tuple[Path, Path]:
    manifest = tmp_path / "guides.yaml"
    manifest.write_text(yaml.safe_dump(MANIFEST), "utf-8")
    site = tmp_path / "site-config"
    site.mkdir()
    (site / "mkdocs.yml").write_text("site_name: Docs\ntheme:\n  name: material\n", "utf-8")
    (site / "index.md").write_text("# Start\n", "utf-8")
    return manifest, site / "mkdocs.yml"


def test_the_navigation_is_the_manifest_in_its_order(tmp_path: Path) -> None:
    manifest, config = configuration(tmp_path)
    build = tmp_path / "build"
    published(
        build,
        "Docs/Using/Second by name, first in order.md",
        "Docs/Using/A page.md",
        "Docs/Running/Installing.md",
    )
    written = yaml.safe_load(docs_site.write(manifest, config, build).read_text("utf-8"))
    assert written["nav"] == [
        {"Start": "index.md"},
        {
            "Using it": [
                {"Second by name, first in order": "Docs/Using/Second by name, first in order.md"},
                {"A page": "Docs/Using/A page.md"},
            ]
        },
        {"Running it": [{"Installing": "Docs/Running/Installing.md"}]},
    ]
    assert written["docs_dir"] == "src"
    assert written["site_dir"] == "site"
    assert written["site_name"] == "Docs"
    assert (build / "src" / "index.md").read_text("utf-8") == "# Start\n"


def test_a_page_the_publication_did_not_write_fails_naming_it(tmp_path: Path) -> None:
    manifest, config = configuration(tmp_path)
    build = tmp_path / "build"
    published(build, "Docs/Using/A page.md", "Docs/Running/Installing.md")
    with pytest.raises(SystemExit, match="use/b"):
        docs_site.write(manifest, config, build)
    assert not (build / "mkdocs.yml").exists()


def test_the_colours_are_the_web_apps_brand_colour_resolved_from_its_tokens() -> None:
    tokens = {
        "primitive": {
            "color": {"indigo": {"300": {"$value": "#B4B5FF"}, "700": {"$value": "#3B2BC4"}}}
        },
        "semantic": {
            "light": {"text": {"brand": {"$value": "{primitive.color.indigo.700}"}}},
            "dark": {"text": {"brand": {"$value": "{primitive.color.indigo.300}"}}},
        },
    }
    css = docs_site.stylesheet(tokens)
    light, dark = css.split('[data-md-color-scheme="slate"]')
    assert "--md-primary-fg-color: #3B2BC4;" in light
    assert "--md-primary-fg-color: #B4B5FF;" in dark
    assert "{" + "primitive" not in css


@pytest.mark.skipif(shutil.which("git") is None, reason="the guides are read from git")
def test_make_docs_site_builds_every_page_with_search(tmp_path: Path) -> None:
    """The make target's three commands, into a directory of the test's own."""
    build = tmp_path / "docs-site"
    manifest = "docs/guides/guides.yaml"
    subprocess.run(  # noqa: S603 — our own entry points, fixed arguments
        [
            shutil.which("taktusctl") or "taktusctl",
            "guides",
            "publish",
            "--manifest",
            manifest,
            "--to",
            str(build / "src"),
            "--repository",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        cwd=ROOT,
    )
    docs_site.write(ROOT / manifest, ROOT / "docs-site" / "mkdocs.yml", build)
    done = subprocess.run(  # noqa: S603
        [
            shutil.which("zensical") or "zensical",
            "build",
            "--config-file",
            str(build / "mkdocs.yml"),
            "--strict",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    site = build / "site"
    assert (site / "index.html").is_file()
    assert (site / "search.json").is_file()
    guides = yaml.safe_load((ROOT / manifest).read_text("utf-8"))["guides"]
    for guide in guides:
        for page in guide["pages"]:
            assert (site.joinpath(*guide["place"], page["title"], "index.html")).is_file(), page[
                "id"
            ]
