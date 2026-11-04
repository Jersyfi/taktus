"""The expiry connector: what expires, read over two open standards.

The capabilities `expiry.certificates`, the certificate a TLS endpoint presents (RFC 8446,
RFC 5280), and `expiry.domains`, a domain's registration over RDAP (RFC 9082, RFC 9083). Nothing
here names a product (ADR-0196).

Run it: `python -m taktus_connectors.expiry --certificate www.example:443 --target https://rdap.example`.
The modules: `declaration` is what it declares, `operations` what it reads, and `server` how the
shared MCP server of `connectors/serving.py` serves it.
"""
