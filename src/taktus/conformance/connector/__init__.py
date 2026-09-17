"""The connector half of the suite: C-01 to C-10 against a live connector over MCP.

Kept free of imports at package level so that `taktus.conformance.report` can look up the
connector catalogue (`rules.CATALOGUE`) without pulling in the suite. The entry point is
`taktus.conformance.run_connector_suite`.
"""
