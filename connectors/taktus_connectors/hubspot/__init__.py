"""The customer system connector: the connector contract v1 over the HubSpot CRM API v3.

The capability `crm.contacts`, scoped: the contacts that carry one address, a contact created
for it, and a note of a touchpoint written on it, both writes `marked`. This directory, its
README and configuration are the only places that name the product. Everywhere else it is the
capability (CLAUDE.md §6, ADR-0209).

Run it: `python -m taktus_connectors.hubspot`.
"""
