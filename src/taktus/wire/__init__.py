"""Wire formats: how bytes on a connection become messages, shared by two readers.

The conformance suite (a client of adapters, no part of the core) and the driven worker
adapter both read Server-Sent Events from a worker. Neither may import the other
(docs/architecture/project-structure.md §3), so the reading lives here, once. Nothing in this
package does I/O, knows a product, or imports anything from the control plane; it is safe for
both to depend on.
"""
