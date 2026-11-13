# Method scaffolds

A method scaffold is a curated skill that names the artifacts a project needs before AI can run
it on its own (UC-13.2, ADR-0307). Each directory under `skills/` is a skill in the open
`SKILL.md` format. Beside its `SKILL.md`, a `scaffold.yaml` declares the artifacts, and
`templates/` holds the file each artifact is created from.

| Scaffold | For |
|---|---|
| `development-scaffold` | a software project: use cases, architecture decisions, a test strategy, a definition of done, a glossary |
| `process-automation-scaffold` | a process to automate: its description, takeover instructions, anchors, evaluation cases, the systems it touches |
| `analysis-scaffold` | an analysis: its question, data sources, method, findings and assumptions |

`taktusctl skill register scaffolds --version 1.0.0` registers all three as drafts with the
origin `curated`. They pass the same lifecycle as every skill: evaluated, approved, put into
production (ADR-0162). An organisation adds a scaffold of its own the same way, from a directory
of the same shape. `taktusctl bundle check` holds a `scaffold.yaml` to its format without an
instance.

A person can use every scaffold without Taktus: read its `SKILL.md`, copy the templates into the
places `scaffold.yaml` names, and look at each artifact's last change by hand.
