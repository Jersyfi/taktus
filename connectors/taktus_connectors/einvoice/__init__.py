"""The documents connector: the connector contract v1 over a document inbox reached by WebDAV,
whose electronic invoices it reads as the business terms of EN 16931.

The capability `documents.invoices`: the documents an organisation received, listed, and one of
them read — in UBL 2.1 or in CII D16B, the two syntaxes of the European standard. Two open
standards and no product: WebDAV (RFC 4918) is what file shares, document stores and many
portals serve a folder over, and EN 16931 what an electronic invoice in the European Union is
(ADR-0169).

Run it: `python -m taktus_connectors.einvoice`. The modules: `declaration` is what it declares,
`operations` how the inbox is asked, `standard` how a document is read, and `server` how the
shared MCP server of `connectors/serving.py` serves it.
"""
