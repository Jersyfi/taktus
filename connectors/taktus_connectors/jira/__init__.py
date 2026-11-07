"""The work tracker connector: the connector contract v1 over the Jira Cloud REST API v3.

The capability `tasks.items`, in the operations and shapes of the `linear` connector: the open
issues of one project, read without their assignee, and a reminder written on one of them,
`marked`. This directory, its README and configuration are the only places that name the
product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0209).

Run it: `python -m taktus_connectors.jira --target https://<site>.atlassian.net --project KEY`.
"""
