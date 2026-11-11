A **gate** is a check that must pass before a change is merged. Each is a `make` target. `make
help` lists every target with one line on what it does.

## Before a commit

```bash
make install   # the environment, from uv.lock
make check     # lint, types, architecture, documentation and register gates, the unit tests
```

`make check` is meant to take under a minute. `make test` runs every test that is not a gate, and `make test
BASE=origin/main` only those the change reaches.

## The gates an adapter or a process meets

| Target | Fails when |
|---|---|
| `make gate-arch` | the core imports a driver or names a product, two components import each other, or a worker or connector imports the core |
| `make gate-contracts` | a schema is invalid, an example does not validate, a must-fail example passes, or a deprecation does not name its removal |
| `make gate-compat` | a contract changed in a way that breaks a consumer of the last release |
| `make gate-conformance` | a worker, connector or model adapter of this repository fails its conformance suite |
| `make gate-exactness` | an `exact` step can take its final value from a variable method |
| `make gate-governance` | an anchor, a limit or a least-privilege rule does not hold |
| `make gate-docs` | a change to a contract, a tool, an adapter or a deployment comes without its documentation |

`make gates` runs everything CI runs. `make verify` runs what CI would select for the change and
records that it passed.

## Tests at the right level

| Directory | What is tested there |
|---|---|
| `tests/components/` | one component's domain and application, against fakes |
| `tests/adapters/` | one adapter against a fake of what it reaches; a connector against `tests/fakes/` |
| `tests/conformance/` | the conformance suites against the shipped workers and connectors |
| `tests/integration/` | the whole path, from a bundle to a finished run |
| `tests/architecture/` | the rules of the adapter obligation and the component boundaries |

A test that needs a credential never runs on a pull request. A connector or a model is proven
against a fake built from the provider's published interface.
