"""The newsletter connector: the connector contract v1 over the Mailchimp Marketing API 3.0.

One capability, `newsletter.broadcasts`: a campaign drafted to one audience, read, and sent once
a person released it. The audience's members never leave the service: no output names an
address.

Run it: `python -m taktus_connectors.mailchimp`. The modules: `declaration` is what it declares,
`operations` how the API is asked, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
