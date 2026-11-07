"""The product analytics connector: the connector contract v1 over the Mixpanel Query API.

One capability, `analytics.reports`: the counts of a project's events per day, week or month,
aggregated, never a person. Run it: `python -m taktus_connectors.mixpanel`. The modules:
`declaration` is what it declares, `operations` how the API is asked, and `server` how the
shared MCP server of `connectors/serving.py` serves it.
"""
