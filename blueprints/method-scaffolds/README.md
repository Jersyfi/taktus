# Method scaffolds

The processes that use the method scaffolds of `scaffolds/` (UC-13.2, ADR-0307, ADR-0308). A
scaffold is a curated skill. It reaches production only through rounds on the evaluation cases
of the processes that use it, as every skill does (ADR-0162). The processes here are those
processes.

| Process | What it does | Scaffold it uses |
|---|---|---|
| [SC-01](processes/SC-01-check-a-development-project.yaml) | checks a software project against the development scaffold, and tells the owner what to write first for each missing or stale artifact | `development-scaffold` |

SC-01 writes nothing outside. Furnishing the missing artifacts — files as a pull request, pages in
the knowledge system — is an act a person asks for: `taktusctl scaffold furnish`, or a process
that calls `orchestrator.scaffolds.furnish`, once the scaffold is in production.

The process-automation and analysis scaffolds have no process here yet. An organisation's process
that names one in `work.skills`, with evaluation cases, lets it reach production the same way.
