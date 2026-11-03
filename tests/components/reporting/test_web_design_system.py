"""The web app's design system and its one navigation list, read from the files (UC-13.7).

ADR-0177: the owner's design tokens, copied unchanged, and Taktus's layer beside them, every
value a primitive; every text and mark measured for contrast in both modes; no colour written
in a page. ADR-0178: every page of the web app belongs to one destination of one list. The web
app's own tests hold the same from its side (`web/src/lib/design.test.ts`,
`web/src/lib/navigation.test.ts`); these hold it where the Python suite runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

WEB = Path(__file__).resolve().parents[3] / "web"
FOUNDATION = json.loads((WEB / "design" / "tokens.json").read_text(encoding="utf-8"))
TAKTUS = json.loads((WEB / "design" / "taktus.tokens.json").read_text(encoding="utf-8"))
REFERENCE = re.compile(r"^\{([^}]+)\}$")


def _node(tree: dict[str, Any], path: str) -> Any:
    node: Any = tree
    for key in path.split("."):
        node = node[key]
    return node


def _resolved(tree: dict[str, Any], value: Any) -> Any:
    for _ in range(8):
        if not (isinstance(value, str) and (m := REFERENCE.match(value))):
            return value
        value = _node(tree, m.group(1))["$value"]
    raise AssertionError(f"a reference cycle at {value}")


def _colour(mode: str, group: str, *names: str) -> str:
    tree = {**FOUNDATION, "semantic": {m: {**FOUNDATION["semantic"][m], **TAKTUS["semantic"][m]} for m in ("light", "dark")}}
    node = tree["semantic"][mode][group]
    for name in names:
        node = node[name]
    value = _resolved(tree, node["$value"])
    assert isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value), value
    return value


def _luminance(hex_colour: str) -> float:
    def channel(i: int) -> float:
        c = int(hex_colour[1 + i : 3 + i], 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4)


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


PLANES = [("bg", "canvas"), ("bg", "surface"), ("bg", "raised"), ("bg", "surface-sunken")]
TEXTS = [("text", n) for n in ("primary", "secondary", "subtle", "brand", "danger", "success", "warning")]
FAMILIES = ("reproducible", "variable", "person", "waiting", "alert")


def test_every_text_reads_at_four_and_a_half_to_one_on_every_plane_in_both_modes() -> None:
    for mode in ("light", "dark"):
        for text in TEXTS:
            for plane in PLANES:
                ratio = _contrast(_colour(mode, *text), _colour(mode, *plane))
                assert ratio >= 4.5, (mode, text, plane, round(ratio, 2))


def test_every_family_s_mark_reads_at_three_to_one_in_both_modes() -> None:
    for mode in ("light", "dark"):
        for family in FAMILIES:
            for plane in PLANES[:2]:
                ratio = _contrast(_colour(mode, "family", family, "hue"), _colour(mode, *plane))
                assert ratio >= 3, (mode, family, plane, round(ratio, 2))


def test_taktus_s_layer_takes_every_value_from_a_primitive_and_never_the_signature() -> None:
    def values(node: Any) -> list[str]:
        if isinstance(node, dict):
            if "$value" in node:
                return [node["$value"]]
            return [v for k, child in node.items() if not k.startswith("$") for v in values(child)]
        return []

    found = values(TAKTUS)
    assert found
    for value in found:
        assert re.fullmatch(r"\{primitive\.color\.[a-z]+\.\d+\}", value), value
        assert "raspberry" not in value
    assert FOUNDATION["$source"].startswith("Copied unchanged from https://github.com/Jersyfi/hubtask")


LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def test_no_page_writes_a_colour_of_its_own() -> None:
    src = WEB / "src"
    found: list[str] = []
    for path in [*src.rglob("*.svelte"), *src.rglob("*.css")]:
        if "generated" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        styles = [text] if path.suffix == ".css" else re.findall(r"<style[^>]*>(.*?)</style>", text, re.DOTALL)
        styles += re.findall(r'\sstyle(?::[\w-]+)?="([^"]*)"', text)
        for style in styles:
            for line in COMMENT.sub("", style).splitlines():
                if LITERAL.search(line):
                    found.append(f"{path.relative_to(WEB)}: {line.strip()}")
    assert found == []


def test_every_page_belongs_to_one_destination_of_the_navigation() -> None:
    navigation = (WEB / "src" / "lib" / "navigation.ts").read_text(encoding="utf-8")
    prefixes = re.findall(r"'(/[a-z/]*)'", " ".join(re.findall(r"routes: \[([^\]]*)\]", navigation)))
    assert prefixes
    routes = WEB / "src" / "routes"
    lost = []
    for page in routes.rglob("+page.svelte"):
        route = "/" + "/".join(page.relative_to(routes).parent.parts)
        if not any(route == p or (p != "/" and route.startswith(p + "/")) for p in prefixes):
            lost.append(route)
    assert lost == []
