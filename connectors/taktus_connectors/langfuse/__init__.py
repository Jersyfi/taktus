"""The evaluation platform connector: the connector contract v1 over Langfuse's public API.

Langfuse is an open-source platform for tracing, evaluating and versioning the prompts of
language models, self-hostable under the MIT licence, with a documented public HTTP API
(ADR-0305, NTC-0278). Three capabilities: `evaluations.records`, a copy of an evaluation's
cases, results and scores, and the scores the platform holds read back; `prompts.versions`, a
prompt mirrored as a version; `observability.costs`, the cost the platform computed for a trace
(UC-5.8). This directory, its README and configuration are the only places that name the
product. Everywhere else it is the capability (CLAUDE.md §6).

Run it: `python -m taktus_connectors.langfuse --target <the platform's address>`. The modules:
`declaration` is what it declares, `operations` how the platform is asked and its answers read,
and `server` how the shared MCP server of `connectors/serving.py` serves it.
"""
