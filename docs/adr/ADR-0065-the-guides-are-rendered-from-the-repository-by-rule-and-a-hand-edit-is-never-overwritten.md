# ADR-0065 — The guides are rendered from the repository by rule, and a hand edit is never overwritten

**Status:** accepted · makes UC-13.6 buildable (issue #88); the `knowledge` component's package
gains its first content

## Context

UC-13.6 asks for two guides beyond the repository: one for the people who administer Taktus, one
for the people who use it. They are read in the organisation's own knowledge system, a wiki or
otherwise. They are generated from the repository and are never a second source of truth: where
the two differ, the repository wins. Every page names its files and its commit. A page edited by
hand in the knowledge system is not overwritten silently. Where the organisation has no knowledge
system, the guides are files it can open without Taktus.

Four questions were open. What a guide is made of, so that it says nothing the repository does
not. Which method produces a page. How Taktus reaches a knowledge system it does not know. And how
it tells its own text from a person's, so that it never overwrites the person's.

## Decision

### 1. The repository declares its guides, and a page is made of the repository's own text

`docs/guides/guides.yaml` is the **manifest**: each guide has an identifier, a title, its reader,
the place it goes in a knowledge system, and its pages. A page is a list of **parts**. A part is a
file of the repository, or one section of it named by its heading. A part may give its section
another heading in the page, where its own would mislead a reader who does not see the file.

Nothing else goes into a page. The files under `docs/guides/` hold only the words a reader of a
guide needs between parts and that no other document says. Everything else is taken from where it
is kept, so that it is written once. The guide for users is mostly such words, because the
repository's documents are written for developers.

### 2. A page is rendered by a rule, and its result is `exact`

Rendering takes each part as the repository holds it at one commit, shifts its headings under the
page's title, turns a link to another file of the repository into the file's path in words, and
closes the page with the files it came from and the commit. The method is `rule`. The result is of
class `exact`: the same commit always gives the same page, and the check is to render it again.

A language model was rejected. A page it wrote would say something the repository does not, which
is the second source of truth the use case forbids. A model may later propose a sentence for
`docs/guides/`, through a pull request like any other change; it never writes a page.

A page that would carry an IP address of an installation or a private key is refused, and so is a
part whose file or section does not exist at the commit. Refused means nothing is rendered.
Loopback addresses and the ranges reserved for examples are no address of an installation.

A page has two digests. **`digest`** is of its whole text. **`content`** is of what it says with the
commit left aside. A commit that changes nothing a page says leaves its content as it was. Such a
page is not rewritten, and it still truthfully names the commit it was generated at.

### 3. The mark: what Taktus keeps beside a page it wrote

Beside every page it writes, Taktus has the knowledge system keep a **mark**: the guide, the page,
the commit, the digest of the text written, and its content. The knowledge system returns it
unchanged. A page whose text no longer hashes to the digest in its mark was edited by hand.

### 4. The capability `knowledge.pages`

Taktus reaches a knowledge system through a connector, by capability (ADR-0003). The capability has
three operations:

| Operation | Effect | Input | Output |
|---|---|---|---|
| `knowledge.pages.list` | read | `place` | `pages`: every page at or below the place, each with `place`, `digest` and `mark` |
| `knowledge.pages.read` | read | `place` | `place`, `body`, `digest`, `mark`; `not_found` where no page is |
| `knowledge.pages.write` | write, `marked` | `place`, `body`, `mark`, `expected` | `place`, `digest` |

A **place** is a list of names, one per level, the last being the page's title. **`digest`** is
the SHA-256 of the page's text as UTF-8, the mark excluded. A write replaces a page only where the
page's digest is `expected`, or where no page is when `expected` is `null`. Otherwise it ends
`conflict`, and nothing is written. The connector keeps the idempotency key beside the page, so a
repeat with the same key and the same text writes nothing and answers `replayed`.

A connector maps a place onto its system's structure. A wiki of shelves, books and pages takes a
place of three names. A directory takes one folder per level and one file per page.

### 5. Seven states, and only two are written

Before writing, each page is measured against what the knowledge system holds
(`components/knowledge/domain/service/pages.py`):

| State | What is held | What happens |
|---|---|---|
| `absent` | nothing | written |
| `current` | Taktus's text, untouched, and the repository says the same | nothing |
| `changed` | Taktus's text, untouched, and the repository says something else | written |
| `edited` | Taktus's text edited by hand; the repository still says what was written | kept, difference reported |
| `outdated` | Taktus's text edited by hand; the repository says something else now | kept, difference reported, shown out of date |
| `foreign` | a page Taktus did not write | kept, difference reported |
| `retired` | a page Taktus wrote that the repository no longer declares | kept, named on the contents page |

A page is overwritten only where it holds exactly the text Taktus last wrote there. The write
names that text's digest, so a person who edits the page between the reading and the writing keeps
the edit. Nothing is deleted: a retired page stays until a person removes it (CLAUDE.md §9).

The **difference** is a unified diff of the page as the knowledge system holds it against the page
as the repository says it. It is what a person changed. The edit reaches the guide only as a
change to the repository.

Every guide gets a **contents page**, generated from the manifest and written by the same rules. It
says who the guide is for and lists every page with its state. A page that was not regenerated is
shown out of date there, where a reader of the guide looks.

### 6. Where the organisation has no knowledge system: a directory

The **directory connector** (`adapters/driven/connectors/directory/`) serves `knowledge.pages` over
one directory, one Markdown file per page. The mark and the key are the file's last line, an HTML
comment a viewer does not show. It runs inside the process that uses it, as the loopback connector
does, because a directory is reached through the file system.

`taktusctl guides check` renders both guides and writes nothing. `taktusctl guides publish --to`
renders them and puts them into a directory by the rules of §5. It prints each page's state and
every difference, and exits `1` when a page was kept because a person's text stands. Both read
every file from the commit through `git`, never from the working tree.

### 7. What follows in other tasks

The daily process — its bundle, trigger, ledger entries and the report of a difference to the
person responsible for the documentation — is issue #198. The connector to the wiki the owner is to
create is issue #197, after NEED-0021.

## Alternatives

- **The guides written by hand in the wiki, checked against the repository.** Rejected: that is
  the second source of truth UC-13.6 forbids, with a check that can only find a difference after
  the fact.
- **A language model writes each page from the repository.** Rejected for §2's reason.
- **Copy whole documents into the wiki.** Rejected: the repository's documents are written for
  developers and sessions. A guide must be ordered for its reader, which a manifest of sections
  does without restating anything.
- **Taktus keeps what it wrote in its own database, not beside the page.** Rejected: a record of
  its own would be a second record of the knowledge system's content (UC-5.5 §3). It would also be
  lost with the instance while the pages remain. The mark travels with the page.
- **Overwrite a hand edit and report it afterwards.** Rejected: the use case says a hand edit is
  not overwritten silently. Reporting after overwriting loses the person's text from the place
  they wrote it.
- **The commit in the content digest.** Rejected: every merge would rewrite every page. A hand edit
  would then look out of date after any commit, which is noise that hides the pages whose sources
  really changed.

## Consequences

- `knowledge` has its first content: the manifest, the rendering, the states and the publishing.
  `docs/architecture/project-structure.md` says so.
- The capability `knowledge.pages` is declared by every connector to a knowledge system.
  `docs/architecture/contracts.md` lists it.
- `docs/guides/` is a documented place of the repository. A change that removes a file or a
  section a page takes from fails `tests/integration/test_guides_command.py`, which renders both
  guides from the repository on every run of the tests.

## Where this promise ends

- **The writing rules are checked in review, not by a rule.** No rule can tell whether a sentence
  holds one idea, or whether a guide for users assumes a technical reader. The guides take most of
  their text from documents already held to `CLAUDE.md` §10, and the words under `docs/guides/`
  are reviewed like any other.
- **The refusal of addresses catches IPv4 literals and private key blocks.** It does not catch a
  host name of an installation, an IPv6 address, or a secret of another shape. That the guides
  carry no secret rests on the repository carrying none, which `make gate-secrets` checks; the
  guides are rendered from nothing else.
- **A mark can be removed or copied by whoever may edit the page.** A page whose mark was removed
  is `foreign` and kept. A mark copied onto another text does not make that text Taktus's: its
  digest does not match, so the page is `edited` and kept. A person who restores Taktus's exact
  text by hand makes the page Taktus's again, which is what it then is.
- **A knowledge system that changes the text it stores makes every page look edited.** The
  promise therefore holds only for a connector that returns the text as it was written, or
  computes `digest` over it. Issue #197 must show that for the wiki.
- **The directory connector checks and replaces a file in two moves.** An editor that saves the
  file between the check and the rename loses that save. The window is the length of one file
  write. A knowledge system with a server checks on its side.
- **A difference reaches whoever runs `taktusctl guides publish`.** It reaches the person
  responsible for the documentation once the daily process of #198 reports it. Until then nothing
  runs on a schedule.
- **One language.** The guides are rendered in the repository's language. Other languages are
  configuration UC-13.6 allows and nothing here provides.
