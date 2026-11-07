# ADR-0285 — A process version leaves Taktus as one package of plain files

**Status:** accepted · extends ADR-0011 (process bundles), ADR-0168 (BPMN), ADR-0180 (takeover
instructions) and ADR-0113 (the skill format) · UC-8.9, UC-6.3 · DEC-0228

## Context

UC-8.9 asks that everything that defines a process — its definition, prompts, skills,
configuration and instructions — can be exported as one package per process, in an open format,
and read without Taktus.

The pieces exist apart. A version is a document (`ProcessVersion`). It is written as BPMN
(ADR-0168). Its takeover instructions say how a person runs it (ADR-0180). Its skills export as
their directories (ADR-0113, ADR-0246). A tenant's export (ADR-0221) moves a whole tenant
between instances, as rows: it is read by an instance, not by a person.

## Decision

### 1. The package

`taktusctl process export <process> --to <file>.zip [--version <v>]` writes one ZIP archive.
Without `--version` it is the active version.

| File | What it is | Format |
|---|---|---|
| `process.json` | the version as its document: steps, methods, work, triggers, inputs, limits, evaluation, autonomy, takeover instructions | JSON |
| `process.bpmn` | the same version as a process model (ADR-0168) | BPMN 2.0 XML |
| `prompts/<step>.md` | the system text and prompt of each step whose work names a prompt | Markdown |
| `instructions.md` | the takeover instructions, in the order the steps run | Markdown |
| `configuration.json` | what an instance provides: model purposes, connector operations, capabilities, credential parameters, inputs, limits | JSON |
| `skills/<name>/` | every skill a step uses, at its version in production | the `SKILL.md` directory |
| `README.md` | what each file is | Markdown |
| `manifest.json` | the SHA-256 of every other file, and the skills that could not be included | JSON |

ZIP, JSON, XML and Markdown are read by tools that exist without Taktus.

### 2. Rules of the package

- **It is a rule.** The same version and the same skills give the same bytes. Every entry
  carries one fixed time, and the entries are in path order (`domain/service/package.py`).
- **No secret.** A credential is named by its parameter, as everywhere (CLAUDE.md §9). No value
  is in the package.
- **No product.** A process names capabilities and purposes (ADR-0003). The package carries
  what the version names, so it names no product either.
- **A missing skill is named.** A skill with no version in production, or whose text the
  catalogue did not keep whole, is not in the package. The README and the manifest name it.
- **The export is recorded.** `process.exported` names the version, the person as actor, and
  the package's digest.

## Alternatives

- **The tenant's export** (ADR-0221). It holds every row and is proven by its chains, so it is
  meant for another instance. Rejected for this purpose: a person cannot read it, and it holds
  far more than one process.
- **The bundle's YAML as the author wrote it.** A registered version keeps its parsed document,
  not the author's text with its comments. The JSON document is what registration produced, and
  it is what runs.

## Consequences

- `process/domain/service/package.py`: the files and the archive.
- `process/application/service/packages.py`: `ProcessPackages`, and `process.exported`.
- `composition/skills.py`: `files_of_version`, the skills of a version at their version in
  production.
- `adapters/driving/cli/process_command.py`: `taktusctl process export`.

## Where this promise ends

- The package is what defines the process, not what it did. Runs, the ledger and evaluations are
  the tenant's export (ADR-0221).
- What a provider keeps — a conversation, a fine-tuned model — is not in it (UC-8.9 §3).
- Reading the package needs no Taktus. `process.json` is the registered document, not a bundle:
  registering it again on an instance is not built.
- The package is written from the command line. A surface in the web app or over REST is not
  built.
