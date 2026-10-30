"""The check connector: an HTTP check with a declared expectation, over the connector contract.

The capability `check.http`: one request to a path of a configured service, judged against the
expectation the call declares, and reported with its outcome and its duration. HTTP is an open
standard; nothing here names a product (ADR-0111).

Run it: `python -m taktus_connectors.httpcheck --target https://service.example`.
The modules: `declaration` is what it declares, `operations` what the check does, and `server`
how the shared MCP server of `connectors/serving.py` serves it.
"""
