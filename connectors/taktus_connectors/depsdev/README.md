# The package licence connector — the deps.dev API v3

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the version records of the deps.dev API v3, a public index of open source packages. This
directory, this file and the configuration that points at it are the only places that name the
product. Everywhere else it is the capability `packages.licences` (ADR-0232).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.depsdev --port 9171
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.deps.dev` by default; point it at the fake under
`tests/fakes/package_index_service.py` to run without a network. Added to an instance by one
entry of `TAKTUS_CONNECTORS`: `packages.licences=http://packages-connector:9171/mcp`.

## The documentation it follows

- the API v3 reference, <https://docs.deps.dev/api/v3/>: GetVersion,
  `GET /v3/systems/{system}/packages/{name}/versions/{version}`, the systems `GO`, `RUBYGEMS`,
  `NPM`, `CARGO`, `MAVEN`, `PYPI`, `NUGET`, every path parameter percent-encoded, PyPI names
  normalised as PEP 503 states, and the answer's `licenses`: SPDX 2.1 expressions, or
  `non-standard`, empty where the index knows none;
- npm's lockfile, <https://docs.npmjs.com/cli/configuring-npm/package-lock-json>: `packages`
  keyed by `node_modules/` paths (versions 2 and 3), `dependencies` nested (version 1), `dev`,
  `link`;
- uv's lockfile, <https://docs.astral.sh/uv/concepts/projects/layout/#the-lockfile>: TOML,
  `[[package]]` with `name`, `version` and `source`;
- pip's requirements files, <https://pip.pypa.io/en/stable/reference/requirements-file-format/>.

## What it declares

One operation, `packages.licences.list`, of effect `read`. It takes `manifest`, the text of a
dependency manifest as the repository connector reads it, `format` — `package-lock.json`,
`uv.lock` or `requirements.txt` — and `limit`, how many packages at most (default 500, at most
2000). It reads every exact version the manifest pins, each once, and asks the index for each:
one request per version. The manifest itself never leaves the connector; only a package's
system, name and version do.

The answer is `packages`, each `{system, name, version, dev, licences, known}`; `unpinned`, the
requirements that name no exact version, which the index cannot answer and the connector does
not guess; and `complete`, whether every package fit within `limit`. A version the index does
not hold, or whose name it refuses, is `known: false` with no licences, not a failure.

A manifest that is not the format it names, a format it does not read, or an empty text is
`invalid`. A throttled or failing index is `unavailable` and retryable.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `PACKAGES_TOKEN` | actions: the **requesting identity's** credential, which the contract requires of every call (C-03); the public index takes no key, so the value is never sent | the file `TAKTUS_CREDENTIAL_PACKAGES_TOKEN_FILE` names, read at the moment of each call, never stored |

`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9171/mcp --scenario connectors/taktus_connectors/depsdev/scenario.json
```

[`scenario.json`](scenario.json) reads the licences of a requirements file of two pinned
versions, and refuses a format the connector does not read as the call that cannot be answered.
It names no write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one check;
`tests/conformance/test_connector_v1_business.py` runs every fault.
