"""The app stores connector: the connector contract v1 over App Store Connect and Google Play.

Every store capability. `stores.beta`: the builds of an app, a build given to a beta group or
a test track, and the testers' feedback where the store publishes it. `stores.releases`: an
app's release read with its review and its staged rollout, the rollout raised or halted, and a
version submitted. `stores.reviews`: an app's customer reviews, read without the reviewer, and
a public response written to one (ADR-0207). Each call names its platform, `ios` or `android`,
and is answered by that platform's store. `expiry.credentials`: when a team's signing
certificates and provisioning profiles expire, never their content (ADR-0203); App Store
Connect alone, since Google Play publishes no such credential.

Run it: `python -m taktus_connectors.appstores`. The modules: `declaration` is what it
declares, `config` its configuration, `auth` how it signs in, `operations` how the stores' APIs
are asked for builds and releases, `reviews` for reviews, `credentials` for signing
credentials, and `server` how the shared MCP server of `connectors/serving.py` serves it.
"""
