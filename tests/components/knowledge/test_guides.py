"""The guides beyond the repository (UC-13.6, ADR-0065): rendered from the repository by rule,
put into a knowledge system through `knowledge.pages`, and never overwriting a hand edit."""

from __future__ import annotations

import pytest
from fakes import FakeKnowledgeSystem

from taktus.components.knowledge.application.service import (
    LIST,
    Publication,
    PublishGuides,
    PublishGuidesHandler,
)
from taktus.components.knowledge.domain.model import Manifest, Mark, Page, Source
from taktus.components.knowledge.domain.service import edits
from taktus.components.knowledge.domain.service.pages import Held, PageState, measure
from taktus.components.knowledge.domain.service.render import RenderRefused, digest, render
from taktus.ports.connector import CallContext, idempotency_key

COMMIT = "a" * 40
LATER = "b" * 40

MANIFEST = Manifest.model_validate(
    {
        "guides": [
            {
                "id": "administration",
                "title": "Administering",
                "reader": "the people who run it",
                "place": ["Taktus", "Administration"],
                "pages": [
                    {
                        "id": "installing",
                        "title": "Installing",
                        "parts": [
                            {"file": "docs/guides/installing.md"},
                            {"file": "README.md", "section": "Running it", "heading": "Start"},
                        ],
                    },
                    {
                        "id": "restoring",
                        "title": "Restoring",
                        "parts": [{"file": "docs/restore.md"}],
                    },
                ],
            },
            {
                "id": "use",
                "title": "Using",
                "reader": "everybody",
                "place": ["Taktus", "Using"],
                "pages": [{"id": "asking", "title": "Asking", "parts": [{"file": "use.md"}]}],
            },
        ]
    }
)

FILES = {
    "docs/guides/installing.md": "An instance is the program and its database.\n",
    "README.md": (
        "# Project\n\nIntro.\n\n## Running it\n\nRun `make up`. See [the setup](deploy/README.md)"
        " and [below](#later) and [the site](https://example.org/x).\n\n### Detail\n\nMore.\n\n"
        "```sh\n# not a heading\n```\n\n## Later\n\nNot taken.\n"
    ),
    "docs/restore.md": "# Restore\n\nNot written down yet.\n",
    "use.md": "You ask in the chat.\n",
}


def reader(files: dict[str, str]):  # type: ignore[no-untyped-def]
    return files.get


def pages_at(commit: str = COMMIT, files: dict[str, str] | None = None) -> tuple[Page, ...]:
    return render(MANIFEST, reader(files or FILES), commit)


SOURCE = Source(file="docs/guides/guides.yaml", digest=digest("manifest"))
CONTEXT = CallContext(
    tenant="default",
    identity="idn_operator",
    run_id="guides-read",
    step_id="read-held",
    attempt=1,
    idempotency_key=idempotency_key("guides-read", "read-held", 1),
    credentials=(),
)


async def publish(system: FakeKnowledgeSystem, pages: tuple[Page, ...], run: str) -> Publication:
    return await PublishGuidesHandler(system).execute(
        PublishGuides(
            tenant="default",
            identity="idn_operator",
            run_id=f"guides-{run}",
            manifest=MANIFEST,
            manifest_source=SOURCE,
            pages=pages,
        )
    )


def by_title(publication: Publication) -> dict[str, tuple[str, str]]:
    return {p.place[-1] + "@" + p.guide: (p.state, p.action) for p in publication.pages}


# --- rendering ------------------------------------------------------------------------------


def test_every_page_of_both_guides_is_rendered_where_the_manifest_puts_it() -> None:
    pages = pages_at()
    assert [(p.guide, p.id) for p in pages] == [
        ("administration", "installing"),
        ("administration", "restoring"),
        ("use", "asking"),
    ]
    assert pages[0].place == ("Taktus", "Administration", "Installing")


def test_a_page_names_every_file_it_was_generated_from_and_the_commit() -> None:
    page = pages_at()[0]
    assert f"at commit `{COMMIT}`" in page.body
    assert '- `docs/guides/installing.md`\n- `README.md`, section "Running it"' in page.body
    assert [s.file for s in page.sources] == ["docs/guides/installing.md", "README.md"]
    assert page.digest == digest(page.body)


def test_a_section_is_taken_to_its_end_with_its_headings_shifted_and_links_in_words() -> None:
    body = pages_at()[0].body
    assert body.startswith("# Installing\n\nAn instance is the program and its database.\n\n")
    assert "## Start\n\nRun `make up`." in body
    assert "the setup (in the repository: `deploy/README.md`)" in body
    assert " and below and [the site](https://example.org/x)." in body
    assert "### Detail" in body
    assert "# not a heading" in body
    assert "Not taken." not in body
    assert "Intro." not in body


def test_a_whole_file_gives_its_title_way_to_the_page() -> None:
    body = pages_at()[1].body
    assert body.startswith("# Restoring\n\nNot written down yet.\n")
    assert "# Restore\n" not in body


def test_the_organisation_configures_where_a_guide_goes() -> None:
    pages = render(MANIFEST, reader(FILES), COMMIT, {"use": ("Handbook", "Taktus")})
    assert pages[2].place == ("Handbook", "Taktus", "Asking")
    with pytest.raises(RenderRefused, match="no guide: elsewhere"):
        render(MANIFEST, reader(FILES), COMMIT, {"elsewhere": ("X",)})


@pytest.mark.parametrize(
    ("files", "reason"),
    [
        ({**FILES, "use.md": None}, "use.md does not exist"),
        ({**FILES, "README.md": "# Project\n"}, "has no section 'Running it'"),
        ({**FILES, "use.md": "Reach it at 10.1.2.3.\n"}, "the address 10.1.2.3"),
        ({**FILES, "use.md": "-----BEGIN RSA PRIVATE KEY-----\n"}, "a private key"),
    ],
)
def test_a_page_that_cannot_be_rendered_as_the_repository_stands_is_refused(
    files: dict[str, str | None], reason: str
) -> None:
    with pytest.raises(RenderRefused, match=reason):
        render(MANIFEST, lambda path: files.get(path), COMMIT)


def test_a_loopback_or_example_address_is_no_address_of_an_installation() -> None:
    files = {**FILES, "use.md": "Open 127.0.0.1:8080, listen on 0.0.0.0, e.g. 192.0.2.7.\n"}
    assert render(MANIFEST, reader(files), COMMIT)


def test_a_commit_that_changes_nothing_a_page_says_leaves_its_content_as_it_was() -> None:
    first, later = pages_at(COMMIT), pages_at(LATER)
    assert first[0].digest != later[0].digest
    assert first[0].content == later[0].content
    changed = pages_at(LATER, {**FILES, "use.md": "You ask in the chat, or by mail.\n"})
    assert changed[2].content != first[2].content


def test_the_manifest_refuses_a_page_that_would_take_the_place_of_the_contents() -> None:
    with pytest.raises(ValueError, match="generated"):
        Manifest.model_validate(
            {
                "guides": [
                    {
                        "id": "g",
                        "title": "G",
                        "reader": "r",
                        "place": ["G"],
                        "pages": [{"id": "contents", "title": "C", "parts": [{"file": "a"}]}],
                    }
                ]
            }
        )


# --- publishing -----------------------------------------------------------------------------


async def test_every_page_is_placed_with_its_mark_and_each_guide_gets_its_contents() -> None:
    system = FakeKnowledgeSystem()
    publication = await publish(system, pages_at(), "one")
    assert {p.action for p in publication.pages} == {"created"}
    assert set(system.pages) == {
        ("Taktus", "Administration", "Installing"),
        ("Taktus", "Administration", "Restoring"),
        ("Taktus", "Administration", "Contents"),
        ("Taktus", "Using", "Asking"),
        ("Taktus", "Using", "Contents"),
    }
    mark = Mark.decode(system.pages[("Taktus", "Using", "Asking")].mark)
    assert mark is not None and (mark.guide, mark.page, mark.commit) == ("use", "asking", COMMIT)
    contents = system.pages[("Taktus", "Administration", "Contents")].body
    assert "For the people who run it." in contents
    assert "- Installing — current\n- Restoring — current" in contents


async def test_a_second_run_at_a_commit_that_changes_nothing_writes_nothing() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    writes = len([c for c in system.calls if c[0].endswith(".write")])
    publication = await publish(system, pages_at(LATER), "two")
    assert {p.action for p in publication.pages} == {"kept"}
    assert len([c for c in system.calls if c[0].endswith(".write")]) == writes
    assert f"`{COMMIT}`" in system.pages[("Taktus", "Using", "Asking")].body


async def test_a_change_in_the_repository_reaches_the_page_it_changes_and_no_other() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    files = {**FILES, "use.md": "You ask in the chat, or by mail.\n"}
    publication = await publish(system, pages_at(LATER, files), "two")
    assert by_title(publication)["Asking@use"] == ("changed", "updated")
    assert by_title(publication)["Installing@administration"] == ("current", "kept")
    body = system.pages[("Taktus", "Using", "Asking")].body
    assert "or by mail" in body and f"`{LATER}`" in body


async def test_a_page_edited_by_hand_is_kept_and_its_difference_reported() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    asking = ("Taktus", "Using", "Asking")
    system.edit(asking, lambda body: body.replace("in the chat", "in the team chat"))
    edited = system.pages[asking].body
    publication = await publish(system, pages_at(LATER), "two")
    (withheld,) = publication.withheld
    assert (withheld.place, withheld.state) == (asking, PageState.EDITED)
    assert withheld.difference is not None
    assert "-You ask in the chat.\n+You ask in the team chat.\n" in withheld.difference
    assert "commit" not in "".join(
        line for line in withheld.difference.splitlines(keepends=True)[2:] if line[0] in "+-"
    )
    assert system.pages[asking].body == edited
    contents = system.pages[("Taktus", "Using", "Contents")].body
    assert "- Asking — edited by hand; it differs from the repository" in contents


async def test_a_page_edited_by_hand_whose_sources_changed_is_shown_out_of_date() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    asking = ("Taktus", "Using", "Asking")
    system.edit(asking, lambda body: body + "\nA note.\n")
    files = {**FILES, "use.md": "You ask in the chat, or by mail.\n"}
    publication = await publish(system, pages_at(LATER, files), "two")
    assert by_title(publication)["Asking@use"] == ("outdated", "withheld")
    assert "or by mail" not in system.pages[asking].body
    contents = system.pages[("Taktus", "Using", "Contents")].body
    assert "- Asking — out of date: edited by hand, and the repository has changed since" in (
        contents
    )


async def test_a_page_taktus_did_not_write_is_never_overwritten() -> None:
    system = FakeKnowledgeSystem()
    restoring = ("Taktus", "Administration", "Restoring")
    system.put_foreign(restoring, "Our own restore notes.\n")
    publication = await publish(system, pages_at(), "one")
    assert by_title(publication)["Restoring@administration"] == ("foreign", "withheld")
    assert system.pages[restoring].body == "Our own restore notes.\n"
    assert "not written by Taktus" in system.pages[("Taktus", "Administration", "Contents")].body


async def test_a_page_edited_between_the_reading_and_the_writing_is_not_overwritten() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    asking = ("Taktus", "Using", "Asking")
    system.before_write = lambda: system.edit(asking, lambda body: "Rewritten by a person.\n")
    files = {**FILES, "use.md": "You ask in the chat, or by mail.\n"}
    publication = await publish(system, pages_at(LATER, files), "two")
    assert by_title(publication)["Asking@use"] == ("outdated", "withheld")
    assert system.pages[asking].body == "Rewritten by a person.\n"


async def test_a_page_no_longer_declared_is_kept_and_named_on_the_contents() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(), "one")
    fewer = tuple(p for p in pages_at(LATER) if p.id != "restoring")
    publication = await publish(system, fewer, "two")
    assert by_title(publication)["Restoring@administration"] == ("retired", "kept")
    assert ("Taktus", "Administration", "Restoring") in system.pages
    contents = system.pages[("Taktus", "Administration", "Contents")].body
    assert "- Restoring — no longer part of this guide" in contents


# --- the daily run: one reading, measured and acted on (ADR-0066) ----------------------------


def test_the_manifest_names_every_file_a_page_takes_from_once() -> None:
    assert MANIFEST.files() == (
        "README.md",
        "docs/guides/installing.md",
        "docs/restore.md",
        "use.md",
    )


async def held_now(system: FakeKnowledgeSystem) -> tuple[Held, ...]:
    listed = await system.call(LIST, CONTEXT, {"place": ["Taktus"]})
    return tuple(
        Held.model_validate({**entry, "place": tuple(entry["place"])})
        for entry in listed.output["pages"]
    )


async def test_measuring_is_a_rule_over_the_pages_and_one_reading() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    asking = ("Taktus", "Using", "Asking")
    system.edit(asking, lambda body: body + "\nA note.\n")
    files = {**FILES, "docs/restore.md": "# Restore\n\nFrom the backup.\n"}
    pages = pages_at(LATER, files)
    reading = {h.place: h for h in await held_now(system)}
    calls = len(system.calls)

    measured = measure(MANIFEST, SOURCE, pages, reading)

    assert measure(MANIFEST, SOURCE, pages, reading) == measured, "same inputs, same result"
    assert len(system.calls) == calls, "measuring reads nothing"
    found = {m.place[-1] + "@" + m.guide: (m.state, m.action) for m in measured}
    assert found == {
        "Installing@administration": ("current", "keep"),
        "Restoring@administration": ("changed", "write"),
        "Contents@administration": ("current", "keep"),
        "Asking@use": ("edited", "withhold"),
        "Contents@use": ("changed", "write"),
    }


async def test_a_publication_acts_on_the_reading_it_was_measured_against() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    files = {**FILES, "use.md": "You ask in the chat, or by mail.\n"}
    pages = pages_at(LATER, files)
    reading = await held_now(system)
    before = len(system.calls)

    publication = await PublishGuidesHandler(system).execute(
        PublishGuides(
            tenant="default",
            identity="idn_operator",
            run_id="guides-two",
            manifest=MANIFEST,
            manifest_source=SOURCE,
            pages=pages,
            held=reading,
        )
    )

    operations = [operation for operation, _ in system.calls[before:]]
    assert LIST not in operations, "the reading it was given is the one it acts on"
    measured = measure(MANIFEST, SOURCE, pages, {h.place: h for h in reading})
    assert [(p.place, p.state) for p in publication.pages] == [(m.place, m.state) for m in measured]
    assert publication.counted() == {"created": 0, "updated": 1, "kept": 4, "withheld": 0}


async def test_a_hand_edit_is_reported_once_under_a_name_derived_from_its_text() -> None:
    system = FakeKnowledgeSystem()
    await publish(system, pages_at(COMMIT), "one")
    asking = ("Taktus", "Using", "Asking")
    system.edit(asking, lambda body: body + "\nA note.\n")
    (first,) = (await publish(system, pages_at(LATER), "two")).withheld
    (again,) = (await publish(system, pages_at(LATER), "three")).withheld
    assert first.held is not None and first.held == again.held
    named = edits.report_id(first.guide, first.page, first.held)
    assert named == edits.report_id(again.guide, again.page, str(again.held))
    assert named.startswith("guides-use-asking-") and len(named) == len("guides-use-asking-") + 12
    system.edit(asking, lambda body: body + "\nAnother.\n")
    (other,) = (await publish(system, pages_at(LATER), "four")).withheld
    assert edits.report_id(other.guide, other.page, str(other.held)) != named
    assert first.difference is not None
    assert "A note." in edits.steps(first.difference)[0]
    assert "Asking" in edits.title(asking, PageState.EDITED)
