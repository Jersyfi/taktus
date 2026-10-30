# Connectors

The connectors Taktus ships: tools and channels behind the connector contract
(`contracts/connector/v1`). Each is an MCP server that reaches one product with a credential the
requesting identity owns. It is named by capability everywhere but in its own directory:
processes bind `repository.pullrequests`, and configuration maps that to a connector here.

Each connector is a separate deployable with an image of its own, as every worker is (DEC-0011,
ADR-0158). None of them is in the control plane's image, and none of them imports the control
plane: the control plane reaches a connector over MCP and nothing else. Adding a connector, or
changing one, changes neither the control plane's image nor another connector's.

## The images

`Dockerfile` has one stage per connector, built on a shared base. The base holds the libraries
— the `connectors` group of `pyproject.toml`, installed from `uv.lock` with its hashes — and the
serving library, `taktus_connectors/serving.py`. A stage adds its own connector's directory and
nothing else. Its entry point is the connector's module; the arguments are the connector's.

    docker build -f connectors/Dockerfile --target github -t taktus-connector-github .
    docker run --rm -p 9100:9100 taktus-connector-github --host 0.0.0.0 --port 9100 ...

The image is named `taktus-connector-<directory>`. A release pushes every one with its version
(`.github/workflows/images.yml`). The chart pulls each beside the control plane's image,
`<image.repository>-connector-<name>` (`deploy/k8s/README.md` §2). The one-server install builds
each from this checkout (`deploy/docker/connectors.py`). The release's list of what it ships
names each connector's image (`src/taktus/composition/shipped.json`), and `taktusctl conformance
list` prints them by capability.

## The connectors

Two connectors are not here: the loopback connector, which serves the instance to its own
processes, and the directory connector, which serves pages as files on the instance's own volume.
What they reach is the instance itself, so they run inside its process
(`src/taktus/adapters/driven/connectors/`).

| Connector | What it is | Status |
|---|---|---|
| [`github/`](taktus_connectors/github/README.md) | the reference connector behind `contracts/connector/v1`: an MCP server against a repository hosting service — issues, pull requests, pipelines, comments as actions with a declared effect and a marked idempotency key; webhook intake verified and normalised into commands; fault injection for the suite. Named by capability everywhere but in its own directory | exists; reached by the daemon's webhook intake; its operations are not yet called from a process (the run's binding is `0.2.0`) |
| [`bookstack/`](taktus_connectors/bookstack/README.md) | `knowledge.pages` against a wiki of shelves, books and pages over MCP, the mark, the key and the digests kept in the page's tags: the wiki the guides are read in (UC-13.6, NEED-0021). Named by capability everywhere but in its own directory | exists; passes the connector suite against a fake of the wiki; not yet deployed on an instance |
| [`mail/`](taktus_connectors/mail/README.md) | `mail.messages` and `channel.mail` over IMAP and SMTP: a read, a send `marked` by its message identifier, a reply; a relay delivers the inbox to the intake, signed, one event per message identifier (ADR-0111) | exists; passes the connector suite against a fake mail server; no process uses it yet |
| [`prometheus/`](taktus_connectors/prometheus/README.md) | `metrics.series` over the Prometheus HTTP query API: a query at a moment or over a range, both `read` (ADR-0111) | exists; passes the connector suite against a fake store; no process uses it yet |
| [`httpcheck/`](taktus_connectors/httpcheck/README.md) | `check.http`: one HTTP request judged against a declared expectation, reported with its outcome and duration (ADR-0111) | exists; passes the connector suite against a fake service; no process uses it yet |
| [`aws/`](taktus_connectors/aws/README.md) | `billing.costs` over the AWS Cost Explorer API: a cloud account's cost per day by service, account or region, each amount as decimal text and each day's total its exact sum, every request signed with the requesting identity's key pair (ADR-0150) | exists; passes the connector suite against a fake that recomputes every signature |
| [`openai/`](taktus_connectors/openai/README.md) | `models.costs` over a model provider's organisation costs API: the cost per day by line item or project, in the shape `billing.costs` has (ADR-0150) | exists; passes the connector suite against a fake of the API; no process uses it yet |
| [`anthropic/`](taktus_connectors/anthropic/README.md) | `models.costs` over a model provider's Admin API cost report: the cost per day by description or workspace, cents turned into dollars exactly, in the shape `billing.costs` has (ADR-0150) | exists; passes the connector suite against a fake of the report; read by the model cost watcher, B-2.01 |
| [`sentry/`](taktus_connectors/sentry/README.md) | `errors.issues` over an error tracker's API: the issues of a period, and one issue, with their counts; never a person's field (ADR-0150) | exists; passes the connector suite against a fake of the API; no process uses it yet |
| [`stripe/`](taktus_connectors/stripe/README.md) | `payments.subscriptions` over a payment provider's API: the subscriptions of a status, and one subscription, with their items; `payments.customers`, scoped, one customer's subscriptions for a case (ADR-0130); never a customer's name, address or payment method (ADR-0150) | exists; passes the connector suite against a fake of the API; no process uses it yet |
| [`vendor/`](taktus_connectors/vendor/README.md) | a vendor's own MCP server behind the contract: its tools served as the operations a manifest declares, with their effect and idempotency; without a manifest only the tools the vendor marks as reading, each a read (ADR-0117) | exists; passes the connector suite against the MCP project's reference time server and a stand-in with tools that write; no process uses it yet |
| `serving.py` | the MCP server, the credential read from its file and the faults the connectors above share | exists |
## How a connector is proven

Each connector passes the conformance suite as a process from this checkout, against a fake of
its product, with every fault it can inject (`tests/conformance`, `make gate-conformance`).
`tests/conformance/test_connector_v1_images.py` runs the same suite against each one from its
image. `tests/architecture` holds the boundary: no connector imports `taktus`, the control plane
imports no connector, and each stage copies only its own directory.
