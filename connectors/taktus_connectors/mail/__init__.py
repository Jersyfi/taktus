"""The mail connector: the connector contract v1 over IMAP and SMTP.

The capability `mail.messages` as actions — read a message, send one — and intake on the
channel `channel.mail`: a message that arrives in the mailbox becomes a command. IMAP and SMTP
are open standards, so nothing here names a product (ADR-0111).

Two processes. The connector serves MCP: `python -m taktus_connectors.mail`.
The relay reads the mailbox and hands every new message to the instance's intake, signed:
`python -m taktus_connectors.mail relay --intake <url>`. The modules:
`declaration` is what it declares, `protocol` how it speaks IMAP and SMTP, `operations` what
each operation does — including how a repeat is recognised — `intake` how a message becomes a
command, `relay` how a message reaches the intake, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
