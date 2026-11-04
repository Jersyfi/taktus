"""The calendar connector: a calendar's entries within a window, over iCalendar or CalDAV.

The capability `calendar.events`: the entries of one calendar whose moment falls within a
window, from an iCalendar file (RFC 5545) or a CalDAV server (RFC 4791), repeating entries
expanded where their rule is plain. Nothing here names a product (ADR-0197).

Run it: `python -m taktus_connectors.calendar --target https://calendar.example`.
The modules: `declaration` is what it declares, `icalendar` how an entry is read, `operations`
how a calendar is asked, and `server` how the shared MCP server of `connectors/serving.py`
serves it.
"""
