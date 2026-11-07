# ADR-0276 — A project is a unit of the structure, and a private one is its owner's alone

**Status:** accepted · extends ADR-0275 · UC-1.6, DEC-0228

## Context

UC-1.6 asks that anyone can create a project — alone, with their team, with a project team or
for the whole company — that brings together the conversations, processes, knowledge, shared
agents, connectors and budget that belong to it. A project is a unit of the structure, and
visibility, sharing and cost follow it. It refers to the organisation's own tickets and
documents and copies nothing. A person's private context is kept apart from the team's and the
company's: nothing of a private project appears in any view, report, session or search of the
company context, and none of its consumption in any of the company's figures. Something leaves a
private project only by the act of the person it belongs to.

## Decision

### 1. A project is a unit at the structure's last level

A project is a `StructureUnit` at the last level the organisation named, with the **circle** it
was created for. Everything ADR-0275 says of a unit holds for it: what is placed in it is seen
from inside it and below it nothing; what it shares, its processes use; its consumption counts in
it and above it.

### 2. Each circle has its place and its condition

- **Alone**: below the creator's own deepest unit, **private**, owned by the creator and with
  the creator as its one member. No right is needed.
- **Team**: below a unit the creator belongs to. No right is needed beyond belonging.
- **Project team**: below a named unit, or the root, with the creator and the members named, each
  an identity of the tenant. No right is needed.
- **Company**: below the root, for a creator one of whose roles holds the right
  `project.company`. A right is a role's, never a person's (UC-7.3).

### 3. A private project is outside every other context

A private unit is never part of an identity's default context (ADR-0275 §3), so nothing placed in
it is seen from the team's or the company's context — not even by its owner, until the owner reads
inside the project by name. Nothing is added below a private project. Its consumption counts in
it alone: the counting of ADR-0275 §6 stops at it.

### 4. Only the owner moves anything across its edge

Placing an object in a private project, and moving one out of it, is refused to anyone but its
owner. Sharing the project — turning it into a project of a team or a project team — is the
owner's act alone, recorded `project.shared`. What it consumed while private stays attributed as
it was; from the act on, it counts above.

### 5. A project refers, it does not copy

A project keeps `Reference`s — a ticket, a document, a repository — as a kind, a link and a
title. The organisation's ticket and knowledge systems stay the record (principle 1).

### 6. Every act on a project is in the ledger

`project.created`, `project.shared` and `project.referred` name the identity that acted, in the
same transaction as the change.

## Alternatives

- **A project as a tag on objects.** A tag would not place an object in exactly one unit, and
  the counting of cost would need a second rule beside the structure's.
- **A private project visible to its owner in every context.** UC-1.6 asks for nothing of it in
  the company context, whoever reads it; the owner reads it from inside.
- **Projects without a level.** The structure's levels are the organisation's; the last one is
  where its projects live, whatever it calls them.

## Consequences

- `OrganisationStructure.create_project`, `share`, `refer`, `projects`, `context_of`;
  `Circle`, `Reference`; `Right.COMPANY_PROJECT`.
- `taktusctl structure project`, `/structure/projects` on the HTTP surface, and the projects
  of the web app's *Structure* page.
- `tests/components/identity/test_structure.py`.

## Where this promise ends

- What is *in* a project is what is placed there (ADR-0275) and what it refers to. A session's
  turns belong to the session (ADR-0277), which belongs to the project.
- Search here is the structure's: what a context sees. A search a connector makes in the
  organisation's own system is that system's, with the participant's own rights there.
- A project is not deleted here. Deleting is asked first (CLAUDE.md §9).
