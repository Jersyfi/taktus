"""The app stores connector: the connector contract v1 over App Store Connect and Google Play.

Two capabilities. `stores.beta`: the builds of an app, a build given to a beta group or a test
track, and the testers' feedback where the store publishes it. `stores.releases`: an app's
release read with its review and its staged rollout, the rollout raised or halted, and a version
submitted. Each call names its platform, `ios` or `android`, and is answered by that platform's
store.

Run it: `python -m taktus_connectors.appstores`. The modules: `declaration` is what it
declares, `auth` how it signs in, `operations` how the stores' APIs are asked, and `server` how
the shared MCP server of `connectors/serving.py` serves it.
"""
