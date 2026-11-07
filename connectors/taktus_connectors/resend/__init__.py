"""The transactional mail connector: the connector contract v1 over the Resend API.

Three capabilities. `mail.messages`: a message read from what the domain received or what was
sent, and a message sent. `channel.mail`: a received message the service's signed webhook
announces becomes an intake event, and is answered in its thread. `newsletter.broadcasts`: a
broadcast to one segment drafted, read, and sent once a person released it.

Run it: `python -m taktus_connectors.resend`. The modules: `declaration` is what it declares,
`api` how the API is asked, `messages` and `broadcasts` the operations, `intake` how a webhook
is verified and read, and `server` how the shared MCP server of `connectors/serving.py` serves
it.
"""
