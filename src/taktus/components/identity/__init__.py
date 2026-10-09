"""Owns tenants, accounts, org structure, channel identity, roles.

In this version: identities with their organisational path and account key, the link from a
channel account to one identity, the link code a person makes that link with, and the
organisation's identity source behind a port (ADR-0040, UC-1.7). The component serves the
identity port (`ports/identity.py`); nothing else maps a sender to an identity, and no
connector holds that mapping (control-plane.md §2). Roles and rights are UC-7.3.
"""
