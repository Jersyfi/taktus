"""The wiki connector: the connector contract v1 against a wiki of shelves, books and pages.

The capability `knowledge.pages` (ADR-0065 §4) — list, read and write the pages of a knowledge
system — against the wiki the guides are read in (UC-13.6, NEED-0021). Everywhere else in this
repository it is named by that capability; the product it talks to appears only here, in
README.md and in configuration.

Run it: `python -m taktus_connectors.bookstack --target <base address>`. The
modules: `declaration` is what it declares, `api` how it talks to the wiki, `operations` what
each operation does — how a place maps onto the wiki's structure, how a repeat is recognised and
how a page Taktus wrote keeps its digest — `faults` what it can be made to do wrong, and
`server` the MCP server that ties them.
"""
