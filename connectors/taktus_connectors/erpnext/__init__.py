"""The books connector: the connector contract v1 over ERPNext's REST API (`accounting.invoices`).

An outgoing invoice the payment provider issued is exported into the books as a draft sales
invoice, which a person of the business checks and submits there. Taktus keeps no books
(ADR-0169, ADR-0314): it proposes into the accounting system and never posts.

Run it: `python -m taktus_connectors.erpnext`. The modules: `declaration` is what it declares,
`operations` how the API is asked, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
