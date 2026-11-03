"""The accounting connector: the connector contract v1 over a generic accounting interface.

Three capabilities of an organisation's own accounting system: `accounting.orders`, what was
ordered or contracted and what was received and invoiced against it; `accounting.bookings`, a
booking proposed for a document, which a person of the organisation posts in that system; and
`payment.release`, a payment a person released, handed to that system's payment run. Taktus
keeps no books (ADR-0169): it reads what the system holds and proposes into it.

The interface is generic, not a product's: four resources over HTTP and JSON, stated in the
README, which an accounting system serves directly or through a bridge of a few lines. A product
connector for one accounting system serves the same capabilities and replaces this one by
configuration.

Run it: `python -m taktus_connectors.accounting`. The modules: `declaration` is what it
declares, `operations` how the interface is asked, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
