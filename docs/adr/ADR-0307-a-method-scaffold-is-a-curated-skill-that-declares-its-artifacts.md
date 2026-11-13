# ADR-0307 — A method scaffold is a curated skill that declares its artifacts, and a project is checked and furnished in the organisation's own systems

**Status:** accepted · extends ADR-0113 (skills are `SKILL.md`), ADR-0162 (the skill lifecycle) and ADR-0065 §4 (the capability `knowledge.pages`) · UC-13.2, NTC-0279

## Context

UC-13.2 asks that Taktus brings the tools a project needs before AI can run it on its own. For
development these are use cases, architecture decisions, a test strategy and a definition of
done. Taktus creates and maintains them together with the person. Such a set of tools is a
**method scaffold**: a curated skill, in the same format and under the same lifecycle as a skill
Taktus learned.

Three things were missing.

- **A format.** ADR-0113 chose `SKILL.md` for a skill and forbids Taktus to add a field to it. A
  scaffold must say which artifacts a project needs, and the file cannot say it.
- **A way to check a project.** A check must name every artifact that is missing or no longer
  maintained. Whether an artifact is maintained depends on when it last changed. The repository
  connector reads files and directories but gives no date. The capability `knowledge.pages`
  gives none either.
- **A way to create the artifacts.** They belong in the organisation's own systems — its
  repository, its knowledge system — and not in a store of Taktus's own.

Two words are used below. An **artifact** is one thing a scaffold says a project needs: a file,
a directory of files, or a page of the knowledge system. A **project** is one place in the
organisation's systems where a scaffold is applied: a branch of the repository and, where the
organisation has one, a place of its knowledge system.

## Decision

### 1. A scaffold is a skill directory with a `scaffold.yaml` beside its `SKILL.md`

A scaffold is a skill directory as ADR-0113 §1 defines it. Its `SKILL.md` is the open format,
unchanged: the instructions say how a person and Taktus create and keep each artifact. Beside it,
the file `scaffold.yaml` declares the artifacts. Other files of the directory are the templates
the artifacts are created from. Every file is part of the skill, so an exported scaffold is a
directory that can be read without Taktus (UC-14.3).

```yaml
scaffold: 1                       # the version of this format
work: development                 # the kind of work, a word of the scaffold's own
artifacts:
  - id: use-cases                 # unique in the scaffold, lowercase, digits, hyphens
    title: Use cases
    why: What the project must achieve, each with how it is verified.
    system: repository            # repository | knowledge
    path: docs/usecases           # repository: a relative path
    shape: directory              # repository: file | directory
    template: templates/use-case.md
    maintained_days: 90           # optional: how long it may stay unchanged
  - id: glossary
    title: Glossary
    why: The words the project uses, each explained once.
    system: knowledge
    page: Glossary                # knowledge: the page's name in the project's place
    template: templates/glossary.md
```

A `template` names a file of the scaffold's own directory. A file artifact is created with the
template's text at its path. A directory artifact is created as the directory with one file, the
template, under the template's own name. A page is created with the template's text. The rule
`parse_scaffold` holds the file to this shape. A skill directory with a `scaffold.yaml` that
does not hold to it is refused at registration, with every finding, as an invalid `SKILL.md` is.

### 2. A scaffold is marked curated, and passes the lifecycle like every skill

A skill directory that carries a `scaffold.yaml` is registered with the origin `curated`. The
origin says that people wrote it on purpose, for the catalogue or for their organisation. It was
not drawn from runs or from corrections. Nothing else of the record differs. A scaffold is a
draft when it is registered. It is evaluated, approved, put into production and falls back as
every skill does (ADR-0162). A draft without a passed round is refused approval, a scaffold
included.

The catalogue ships three scaffolds, under `scaffolds/skills/` of this repository:
`development-scaffold`, `process-automation-scaffold` and `analysis-scaffold`. An organisation
adds one of its own by writing such a directory and registering it, `taktusctl skill register
PATH --version V`. No code is written for it.

### 3. A project is checked by rule against its scaffold

The check reads, for every artifact, whether it is there and when it last changed:

- **A repository artifact** through `repository.files.dates`, a new operation of the capability
  `repository.files` (§5). One call answers every path at one commit, with the date of the last
  commit that changed it, and the date of the commit itself.
- **A page** through `knowledge.pages.list` at the page's place, whose entries now carry the
  moment the knowledge system last changed the page (§5).

The rule `examine` then names each artifact with one of four states:

| State | When |
|---|---|
| `present` | it is there, and it is maintained or declares no `maintained_days` |
| `missing` | it is not there: no file, a directory with no file below it, or no page |
| `unmaintained` | it is there, and the project's newest change is more than `maintained_days` after the artifact's last change |
| `unread` | its system could not be read: no connector serves the capability, or the call failed |

The **project's newest change** is the latest of two dates: the commit the check read the
repository at, and the newest change of a page it read. An artifact is measured against the
project, never against the calendar. A project nobody works on does not turn its artifacts
stale. An artifact that stayed unchanged while the project moved on does turn stale (NTC-0279).

A check reads the scaffold at its version in production, or else at its newest version that is
neither retired nor private. The result names that version and its stage. A check reads and
writes nothing outside, so a draft may be read by it.

### 4. A project is furnished in the organisation's own systems

Furnishing creates every artifact that the check finds `missing`, and nothing else. An artifact
that is present or unmaintained is never overwritten: whether its content is right stays with the
person (UC-13.2 §3).

- **Repository artifacts** arrive as one proposal. One branch is created from the project's
  branch with every missing file on one commit (`repository.branches.create`). One pull request
  is opened onto the project's branch (`repository.pullrequests.open`). A person merges it. Taktus
  creates the structure together with the person and does not put it in place by itself.
- **Pages** are written into the project's place with `knowledge.pages.write`, with `expected`
  `null`. A page that appeared between the check and the write is a conflict and is kept.

Only a scaffold version in production furnishes a project. Furnishing acts outside, and a
curated skill acts outside only after the same approval as any other. Every write carries an
idempotency key derived from the caller's run identifier and the artifact
(`taktus.ports.connector.idempotency_key`). A repeat after a restart therefore creates nothing
twice.

### 5. Two compatible additions to connector operations

- **`repository.files.dates`**, capability `repository.files`, effect `read`. Input: `paths`, up
  to 100, and `ref`. The ref is resolved to a commit once, and every path is read at that commit.
  Output: `ref`, `commit`, `committed_at` (the commit's own date) and `files`, each with `path`,
  `changed_at` and `changed_in`. Those are the date and the commit of the last commit at or
  before the resolved one that changed anything at or below the path. A path that nothing ever
  changed is answered with `null` for both. Demand: one request to resolve the ref, one for the
  commit's date, and one per path.
- **`knowledge.pages.list`** entries carry `changed_at`: when the knowledge system last changed
  the page, or `null` where the system does not say. A reader that does not know the field
  ignores it. The guides (ADR-0066) read `place`, `digest` and `mark` as before.

Both are additions. No operation, input or output field that existed changes its meaning.

### 6. Where it lives

| Part | Where |
|---|---|
| `Scaffold`, `ScaffoldArtifact`, `ArtifactState`, `ProjectCheck` | `components/catalog/domain/model/scaffold.py` |
| `parse_scaffold`, `examine`, `to_create` | `components/catalog/domain/service/scaffolds.py` |
| `scaffold_of` — the YAML read, then `parse_scaffold`; `bundle check` holds it too | `adapters/driving/cli/bundle_command.py` |
| `InstanceScaffolds` — which version is read, the connectors resolved | `composition/scaffolds.py` |
| `ScaffoldProjects` — check and furnish over the connector port | `components/catalog/application/service/scaffolds.py` |
| the curated origin at registration | `composition/skills.py` |
| the shipped scaffolds | `scaffolds/skills/` |

The application service takes two `ActionConnector`s, one for the repository and one for the
knowledge system, as the guides' publishing does (ADR-0065). The composition root resolves them
by capability; neither is named by product.

### 7. Method and exactness

| Part | Method | Exactness | Reason | Rejected |
|---|---|---|---|---|
| parsing `scaffold.yaml` | `rule` | `exact` | the format's own rules | none |
| the state of an artifact | `rule` | `exact` | two dates and a declared window, recomputable by a person | `llm` — whether a file is stale is not a matter of judgement here; `statistics` — one project has no population to compare |
| what furnishing creates | `rule` | `exact` | the missing artifacts and their templates, copied as they are | `llm` drafting the content — a scaffold makes sure the structure is there, the content stays with the person (UC-13.2 §3) |

Every part has the same fallback: a person reads the scaffold's `SKILL.md` and `scaffold.yaml`
and creates or checks the artifacts by hand (UC-4.12).

## Alternatives

- **The artifacts in the `SKILL.md` front matter.** Rejected by ADR-0113 §1: Taktus adds no field
  to the file.
- **A scaffold as a blueprint.** Rejected: UC-13.2 keeps the definition's reading. A scaffold is a
  curated skill; one at the level of a domain is a blueprint (UC-15.1).
- **A store of Taktus's own for the artifacts.** Rejected: UC-13.2 asks for the organisation's own
  systems.
- **Staleness against the calendar.** Rejected: a project at rest would raise findings nobody can
  act on.
- **Committing the artifacts onto the project's branch directly.** Rejected: the person creates the
  structure with Taktus. A proposal they merge keeps the act with them.
- **Dates from the history of every file, read by the caller one commit at a time.** Rejected: the
  service answers the last change of a path in one request.

## Consequences

- `OriginKind` gains `curated`. The document of a skill version holds the origin, so no migration
  is needed.
- The repository connector declares `repository.files.dates`, and its fake service answers the
  service's commit history by path. The wiki connector and the directory connector add
  `changed_at` to `knowledge.pages.list`.
- Three scaffolds ship with the catalogue.

## Where this promise ends

A check names what is there and when it changed. It does not read whether the content is right
or complete: a use case without a verification condition is present. A directory counts as there
when one file lies below it. The window is measured against the project's newest change as the
check read it. A project whose repository moves only through a branch the check does not read
appears unchanged.

The date of a repository artifact is the date of the last commit that changed it, as the
service records it. A commit written with a false date gives a false answer. A page's date is
the knowledge system's own. The directory connector gives the file's modification time, which a
copy of the directory can change.

Furnishing creates the files and pages from templates. A template is a structure with
placeholders, not content. Repository artifacts arrive as a pull request, and nothing checks that
a person merges it. A page needs the shelf and the book of the project's place to exist; the
connector creates pages only, and a missing book is `not_found`. Nothing furnishes a project on a
schedule or by itself. The check and the furnishing are acts a caller asks for, through the
application service. No process of a blueprint runs them yet, and the loopback connector does not
serve them.

A scaffold reaches production through rounds on the cases of the processes that use it, as every
skill does. A scaffold no process uses with evaluation cases stays a draft. It can be checked
against, and it cannot furnish a project.
