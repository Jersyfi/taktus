"""A post's HTML as Portable Text, the block content a Sanity document stores.

The processes write a post in plain HTML: paragraphs, headings, lists and the emphasis inside
them (B-8.08). Each becomes a block of the block type's defaults: style `normal`, `h1` to `h6`
or `blockquote`; a list item with `listItem` `bullet` or `number` and its `level`; the
decorators `strong`, `em`, `code`, `underline` and `strike-through`. Any other element keeps
its text and loses its markup; a link keeps its text and loses its address, so that nothing the
connector was not asked to write becomes a link; a script or a style keeps nothing.

Every `_key` is the block's and the span's position, so that the same HTML always gives the
same blocks.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

type Json = dict[str, Any]

WHITESPACE = re.compile(r"\s+")

STYLES = {"p": "normal", "blockquote": "blockquote"} | {f"h{n}": f"h{n}" for n in range(1, 7)}
LISTS = {"ul": "bullet", "ol": "number"}
DECORATORS = {
    "strong": "strong",
    "b": "strong",
    "em": "em",
    "i": "em",
    "code": "code",
    "u": "underline",
    "s": "strike-through",
    "del": "strike-through",
}
SILENT = frozenset({"script", "style", "head", "title"})


class _Blocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Json] = []
        self.lists: list[str] = []
        self.marks: list[str] = []
        self.styles: list[str] = []
        self.silent = 0
        self.current: Json | None = None

    def _open(self) -> Json:
        if self.current is None:
            block: Json = {
                "_type": "block",
                "_key": f"b{len(self.blocks)}",
                "style": self.styles[-1] if self.styles else "normal",
                "markDefs": [],
                "children": [],
            }
            if self.lists:
                block["listItem"] = self.lists[-1]
                block["level"] = len(self.lists)
            self.current = block
        return self.current

    def _close(self) -> None:
        block, self.current = self.current, None
        if block is None:
            return
        children = block["children"]
        while children and not children[-1]["text"].strip():
            children.pop()
        if children:
            children[0]["text"] = children[0]["text"].lstrip()
            children[-1]["text"] = children[-1]["text"].rstrip()
            self.blocks.append(block)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SILENT:
            self.silent += 1
        elif tag in STYLES:
            self._close()
            self.styles.append(STYLES[tag])
        elif tag in LISTS:
            self._close()
            self.lists.append(LISTS[tag])
        elif tag == "li":
            self._close()
        elif tag == "br":
            self.handle_data("\n")
        elif tag in DECORATORS:
            self.marks.append(DECORATORS[tag])

    def handle_endtag(self, tag: str) -> None:
        if tag in SILENT:
            self.silent = max(0, self.silent - 1)
        elif tag in STYLES:
            self._close()
            if self.styles:
                self.styles.pop()
        elif tag in LISTS:
            self._close()
            if self.lists:
                self.lists.pop()
        elif tag == "li":
            self._close()
        elif tag in DECORATORS and DECORATORS[tag] in self.marks:
            self.marks.reverse()
            self.marks.remove(DECORATORS[tag])
            self.marks.reverse()

    def handle_data(self, data: str) -> None:
        if self.silent:
            return
        if self.current is None and not data.strip():
            return
        block = self._open()
        children = block["children"]
        marks = sorted(set(self.marks))
        text = data if data == "\n" else WHITESPACE.sub(" ", data)
        if children and children[-1]["marks"] == marks:
            children[-1]["text"] += text
            return
        children.append(
            {
                "_type": "span",
                "_key": f"{block['_key']}s{len(children)}",
                "text": text,
                "marks": marks,
            }
        )


def blocks(html: str) -> list[Json]:
    """The HTML as Portable Text blocks; text outside any element is a paragraph."""
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    parser._close()
    return parser.blocks
