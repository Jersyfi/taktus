"""Rendering the guides from the repository: a rule, never a model (ADR-0065).

A page is its parts, taken as the repository holds them at one commit, and a closing block that
names every file and the commit. Three things change on the way, and nothing else:

- headings are shifted, so that a section sits under the page's title wherever it came from,
  and a section takes the heading the manifest gives it, where it gives one;
- a link to another file of the repository becomes the file's path in words, because a reader of
  a knowledge system cannot follow a path relative to a checkout; a link to a heading of the same
  file keeps only its words; a link with a scheme stays;
- a fenced block is copied as it is, links and headings in it included.

A page that would carry an address of an installation or a key is refused, and so is a part
whose file or section does not exist at the commit. Refused means nothing is rendered: a guide
missing a page is worse than a run that stops and says why.
"""

from __future__ import annotations

import hashlib
import ipaddress
import posixpath
import re
from collections.abc import Callable, Mapping

from taktus.components.knowledge.domain.model.guide import (
    Guide,
    Manifest,
    Page,
    PageSpec,
    Part,
    Source,
)

HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r"^[ \t]*(```|~~~)")
LINK = re.compile(r"(!?)\[([^\]\n]+)\]\(([^)\s]+)(?:[ \t]+\"[^\"\n]*\")?\)")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?!\.?\d)")
KEY_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")

DOCUMENTATION_NETWORKS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)
"""The ranges reserved for examples (RFC 5737): an address there names no installation."""

type Reader = Callable[[str], str | None]
"""The text of a repository file at the commit being rendered, or None where it does not
exist there."""


class RenderRefused(Exception):
    """A page cannot be rendered as the repository stands; the message names page and cause."""


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def render(
    manifest: Manifest,
    read: Reader,
    commit: str,
    places: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[Page, ...]:
    """Every page of every guide, in the manifest's order. `places` is the organisation's
    configuration: where each guide goes, by its identifier; a guide it does not name goes where
    the manifest puts it."""
    unknown = sorted(set(places or {}) - {guide.id for guide in manifest.guides})
    if unknown:
        raise RenderRefused(f"a place is configured for no guide: {', '.join(unknown)}")
    pages: list[Page] = []
    for guide in manifest.guides:
        place = (places or {}).get(guide.id, guide.place)
        for spec in guide.pages:
            pages.append(render_page(guide, spec, read, commit, place))
    return tuple(pages)


def render_page(
    guide: Guide, spec: PageSpec, read: Reader, commit: str, place: tuple[str, ...]
) -> Page:
    where = f"{guide.id}/{spec.id}"
    blocks: list[str] = []
    sources: list[Source] = []
    for part in spec.parts:
        text = read(part.file)
        if text is None:
            raise RenderRefused(f"{where}: {part.file} does not exist at {commit}")
        taken = _take(text, part, where)
        sources.append(Source(file=part.file, section=part.section, digest=digest(taken)))
        blocks.append(_relink(taken, part.file).strip("\n"))
    said = f"# {spec.title}\n\n" + "\n\n".join(blocks) + "\n\n"
    body = said + closing(sources, commit)
    _refuse_what_must_not_leave(body, where)
    return Page(
        guide=guide.id,
        id=spec.id,
        title=spec.title,
        place=(*place, spec.title),
        body=body,
        commit=commit,
        sources=tuple(sources),
        digest=digest(body),
        content=content(said, sources),
    )


def content(said: str, sources: list[Source] | tuple[Source, ...]) -> str:
    """The digest of what a page says and what it says it from, its commit left aside."""
    named = "\n".join(f"{s.file}\t{s.section or ''}\t{s.digest}" for s in sources)
    return digest(said + "\n" + named)


def closing(sources: list[Source] | tuple[Source, ...], commit: str) -> str:
    """The block that ends every page: what it was generated from, and where a change goes."""
    lines = [
        "---",
        "",
        f"This page is generated from the Taktus repository at commit `{commit}`, from:",
        "",
    ]
    for source in sources:
        section = f', section "{source.section}"' if source.section else ""
        lines.append(f"- `{source.file}`{section}")
    lines += [
        "",
        "The repository is the source of this page. A change made here is not overwritten: it is "
        "reported as a difference from the repository. It reaches this page only as a change to "
        "the repository.",
        "",
    ]
    return "\n".join(lines)


def _take(text: str, part: Part, where: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    if part.section is None:
        return _shift(_drop_title(lines))
    start, level = _find(lines, part.section)
    if start is None:
        raise RenderRefused(f"{where}: {part.file} has no section {part.section!r}")
    end = len(lines)
    fenced = False
    for index in range(start + 1, len(lines)):
        if FENCE.match(lines[index]):
            fenced = not fenced
            continue
        match = None if fenced else HEADING.match(lines[index])
        if match is not None and len(match.group(1)) <= level:
            end = index
            break
    taken = lines[start:end]
    if part.heading is not None:
        taken[0] = "#" * level + " " + part.heading
    return _shift(taken)


def _find(lines: list[str], heading: str) -> tuple[int | None, int]:
    fenced = False
    for index, line in enumerate(lines):
        if FENCE.match(line):
            fenced = not fenced
            continue
        match = None if fenced else HEADING.match(line)
        if match is not None and match.group(2).strip() == heading:
            return index, len(match.group(1))
    return None, 0


def _drop_title(lines: list[str]) -> list[str]:
    """A whole file's own title gives way to the page's."""
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            return lines[index + 1 :]
        break
    return lines


def _shift(lines: list[str]) -> str:
    """The highest heading becomes a heading of the second level, the others follow it."""
    levels: list[int] = []
    fenced = False
    for line in lines:
        if FENCE.match(line):
            fenced = not fenced
            continue
        match = None if fenced else HEADING.match(line)
        if match is not None:
            levels.append(len(match.group(1)))
    if not levels:
        return "\n".join(lines)
    delta = 2 - min(levels)
    shifted: list[str] = []
    fenced = False
    for line in lines:
        if FENCE.match(line):
            fenced = not fenced
            shifted.append(line)
            continue
        match = None if fenced else HEADING.match(line)
        if match is None:
            shifted.append(line)
            continue
        level = min(6, len(match.group(1)) + delta)
        shifted.append("#" * level + " " + match.group(2).strip())
    return "\n".join(shifted)


def _relink(text: str, file: str) -> str:
    out: list[str] = []
    fenced = False
    for line in text.split("\n"):
        if FENCE.match(line):
            fenced = not fenced
            out.append(line)
            continue
        out.append(line if fenced else LINK.sub(lambda m: _link(m, file), line))
    return "\n".join(out)


def _link(match: re.Match[str], file: str) -> str:
    image, words, target = match.group(1), match.group(2), match.group(3)
    if SCHEME.match(target):
        return match.group(0)
    if target.startswith("#"):
        return words
    path = posixpath.normpath(posixpath.join(posixpath.dirname(file), target.split("#")[0]))
    if image:
        return f"(an image in the repository: `{path}`)"
    if words.strip("`").rstrip("/") in (path, posixpath.basename(path)):
        return f"`{path}`"
    return f"{words} (in the repository: `{path}`)"


def _refuse_what_must_not_leave(body: str, where: str) -> None:
    if KEY_BLOCK.search(body):
        raise RenderRefused(f"{where}: the page would carry a private key")
    for found in IPV4.findall(body):
        try:
            address = ipaddress.ip_address(found)
        except ValueError:
            continue
        if address.is_loopback or address.is_unspecified:
            continue
        if any(address in network for network in DOCUMENTATION_NETWORKS):
            continue
        raise RenderRefused(f"{where}: the page would carry the address {found}")
