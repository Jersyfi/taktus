"""The instance runs a conformance suite itself: the catalog's `Suites` port over the suites in
`taktus.conformance` and the instance's own configuration (ADR-0044).

For an adapter identifier, the endpoint is the one the configuration resolves for it, never one
a caller names:

- `worker.<name>` or `worker.<kind>`: each configured worker separately (ADR-0078). One reached
  by endpoint is run against its endpoint (`TAKTUS_WORKER`, or `--worker` for `taktusctl`, for
  the unnamed worker). One of a launched kind: one execution unit started for the suite through
  the execution port, at autonomy level 1 and with no host, and ended after it. The suite's
  task, the hosts it reaches, the name of the credential W-08 searches for and a log the
  instance can read are `conformance.worker.task`, `.hosts`, `.credential` and `.log`, read as
  the worker reads its configuration: its own first, the instance's otherwise; the credential
  is the worker's own. How long one assignment may take, and how long the suite waits between two
  events, are `conformance.timeout` and `conformance.idle.timeout`; the suite's own defaults
  apply where they are not set.
- `connector.<label>`: the MCP URL `TAKTUS_CONNECTORS` maps the label to. The suite needs a
  scenario (`contracts/connector/v1/CONFORMANCE.md` §2); the instance reads its path under the
  configuration key `conformance.connector.<label>.scenario`. The suite writes into the target
  the scenario names, so that target must be a sandbox (NEED-0019).
- `model.endpoint`: the model endpoint and model name the instance is configured with, and the
  declaration the model adapter makes for it.

The credential values a suite searches for (W-08, C-04) are read the way an execution adapter
reads a credential: under `credential.<name>`, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE`
names. They are handed to the suite in memory and never written anywhere.

The configuration a pass names is what `Pools.configuration` reads for the identifier — the
same reading the run's maturity threshold compares it with.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from taktus.adapters.driven.execution._common import credential_key
from taktus.components.catalog.domain.model import Configuration, Family
from taktus.components.catalog.ports import NotConfigured, NotRunnable, SuiteRun
from taktus.composition.execution import execution_of, worker_unit
from taktus.composition.pools import Pools
from taktus.composition.settings import ExecutionKind, WorkerSettings
from taktus.conformance import (
    ConnectorSuiteOptions,
    ModelSuiteOptions,
    Report,
    SuiteOptions,
    run_connector_suite,
    run_model_suite,
    run_suite,
)
from taktus.conformance.suite import DEFAULT_CREDENTIAL
from taktus.ports.configuration import Configuration as Settings
from taktus.ports.configuration import ConfigurationError
from taktus.ports.execution import ExecutionError, ExecutionRefused, JobRequest
from taktus.ports.worker import CredentialReference

type WorkerTarget = Callable[[], AbstractAsyncContextManager[str]]
"""Where the configured worker answers for the length of one suite: an endpoint, or a unit
started for it and ended after."""


@dataclass(frozen=True)
class WorkerSuite:
    """What the suite of one configured worker needs: where the worker answers, and the
    configuration as that worker reads it — its suite settings and its own credential."""

    target: WorkerTarget
    settings: Settings


CONTRACTS: Mapping[str, str] = {
    "worker": "worker/v1",
    "connector": "connector/v1",
    "model": "model/v1",
}


def taktus_version() -> str:
    """The version of the installed Taktus, whose suite runs."""
    try:
        return version("taktus")
    except PackageNotFoundError:
        return "unknown"


def worker_target(
    worker: WorkerSettings,
    configuration: Settings,
    *,
    state_dir: Path,
    endpoint: str | None = None,
) -> WorkerTarget:
    """Where one configured worker answers for one suite. Kind `endpoint`: the endpoint, which
    `endpoint` overrides for the unnamed worker as it does for the run (`taktusctl --worker`).
    A launched kind: one unit started through the execution port at autonomy level 1, with no
    host and with the conformance credential when the worker has one, and ended after the
    suite. `configuration` is the worker's own (`WorkerSettings.configuration`)."""
    settings = worker.execution
    if settings.kind is ExecutionKind.ENDPOINT:
        address = (endpoint if worker.name is None else None) or settings.endpoint

        @asynccontextmanager
        async def running() -> AsyncIterator[str]:
            yield address

        return running

    @asynccontextmanager
    async def launched() -> AsyncIterator[str]:
        name = configuration.get("conformance.worker.credential") or DEFAULT_CREDENTIAL
        credentials: tuple[CredentialReference, ...] = ()
        if configuration.secret(credential_key(name)) is not None:
            credentials = (CredentialReference(name=name, injected_as="env"),)
        request = JobRequest(
            job_id=f"conformance-{secrets.token_hex(6)}",
            unit=worker_unit(worker),
            autonomy_level=1,
            credentials=credentials,
        )
        execution = execution_of(settings, configuration, state_dir=state_dir)
        try:
            async with execution.launch(request) as job:
                yield job.endpoint
        except (ExecutionRefused, ExecutionError) as error:
            raise NotRunnable(
                f"the execution unit for the suite could not be started: {error}"
            ) from error

    return launched


def worker_suites(
    workers: Sequence[WorkerSettings],
    configuration: Settings,
    *,
    state_dir: Path,
    endpoint: str | None = None,
) -> dict[str, WorkerSuite]:
    """The suite of every configured worker, by its adapter identifier."""
    suites: dict[str, WorkerSuite] = {}
    for worker in workers:
        own = worker.configuration(configuration)
        target = worker_target(worker, own, state_dir=state_dir, endpoint=endpoint)
        suites[worker.identifier] = WorkerSuite(target=target, settings=own)
    return suites


class InstanceSuites:
    """The `Suites` port of the catalog, over one instance's configuration."""

    def __init__(
        self,
        *,
        pools: Pools,
        settings: Settings,
        workers: Mapping[str, WorkerSuite],
        connectors: Mapping[str, str],
        model_endpoint: str | None,
    ) -> None:
        self._pools = pools
        self._settings = settings
        self._workers = workers
        self._connectors = connectors
        self._model_endpoint = model_endpoint

    async def run(self, integration: str) -> SuiteRun:
        family = integration.split(".", 1)[0]
        if family not in CONTRACTS:
            raise NotRunnable(
                f"{integration} has no contract suite: the conformance half is earned by "
                "workers, connectors and models"
            )
        configuration = await self._configuration(integration)
        if family == "worker":
            report = await self._worker_suite(integration)
        elif family == "connector":
            report = await self._connector_suite(integration)
        else:
            report = await self._model_suite(integration)
        return SuiteRun(
            integration=integration,
            family=_family(family),
            contract=report.contract,
            taktus_version=taktus_version(),
            configuration=configuration,
            report=report.to_dict(),
        )

    async def _configuration(self, integration: str) -> Configuration:
        """What stands behind the identifier as the run reads it. An adapter whose declaration
        cannot be read is still run against — the suite says why — and the configuration names
        the adapter alone."""
        try:
            found = await self._pools.configuration(integration)
        except Exception:
            return Configuration(adapter=integration)
        if found is None:
            raise NotConfigured(f"no configured adapter {integration!r}")
        return found

    async def _worker_suite(self, integration: str) -> Report:
        suite = self._workers.get(integration)
        if suite is None:
            raise NotConfigured(f"no configured adapter {integration!r}")
        settings = suite.settings
        task_path = settings.get("conformance.worker.task")
        task = _json(task_path, settings.name("conformance.worker.task"))
        hosts = tuple(
            h.strip() for h in (settings.get("conformance.worker.hosts") or "").split(",")
        )
        name = settings.get("conformance.worker.credential") or DEFAULT_CREDENTIAL
        log = settings.get("conformance.worker.log")
        async with suite.target() as endpoint:
            return await run_suite(
                SuiteOptions(
                    endpoint=endpoint,
                    task=task,
                    hosts=tuple(h for h in hosts if h),
                    credential_name=name,
                    credential_value=_credential(settings, name),
                    worker_log=None if log is None else Path(log),
                    timeout=self._seconds("conformance.timeout", 300.0),
                    idle_timeout=self._seconds("conformance.idle.timeout", 60.0),
                )
            )

    async def _connector_suite(self, integration: str) -> Report:
        label = integration.removeprefix("connector.")
        endpoint = self._connectors.get(label)
        if endpoint is None:
            raise NotConfigured(f"no configured adapter {integration!r}")
        key = f"conformance.connector.{label}.scenario"
        path = self._settings.get(key)
        if path is None:
            raise NotRunnable(
                f"{integration} has no scenario: set {self._settings.name(key)} to the scenario "
                "file the suite runs (contracts/connector/v1/CONFORMANCE.md §2); the suite "
                "writes into the target it names, so point it at a sandbox"
            )
        scenario = _json(path, self._settings.name(key)) or {}
        names = [v for v in scenario.get("credentials", {}).values() if isinstance(v, str)]
        values = {
            name: value
            for name in names
            if (value := _credential(self._settings, name)) is not None
        }
        log = self._settings.get(f"conformance.connector.{label}.log")
        return await run_connector_suite(
            ConnectorSuiteOptions(
                endpoint=endpoint,
                scenario=scenario,
                credential_values=values,
                adapter_log=None if log is None else Path(log),
                scenario_dir=Path(path).parent,
                timeout=self._seconds("conformance.timeout", 60.0),
            )
        )

    async def _model_suite(self, integration: str) -> Report:
        member = self._pools.models.member(integration)
        if member is None or self._model_endpoint is None:
            raise NotConfigured(f"no configured adapter {integration!r}")
        _, model, name = member
        declaration: dict[str, Any] = {"contract": "model/v1", **model.calculability().document()}
        return await run_model_suite(
            ModelSuiteOptions(
                endpoint=self._model_endpoint,
                model=name or "",
                declaration=declaration,
                credential_value=self._model_credential(),
                timeout=self._seconds("conformance.timeout", 120.0),
            )
        )

    def _seconds(self, key: str, default: float) -> float:
        """A timeout in seconds; the suite's own default when none is configured."""
        value = self._settings.get(key)
        if value is None:
            return default
        try:
            seconds = float(value)
        except ValueError:
            raise NotRunnable(
                f"{self._settings.name(key)}: {value!r} is not a number of seconds"
            ) from None
        if seconds <= 0:
            raise NotRunnable(f"{self._settings.name(key)}: {value!r} is not above zero")
        return seconds

    def _model_credential(self) -> str | None:
        try:
            secret = self._settings.secret("credential.model_api_key")
        except ConfigurationError as error:
            raise NotRunnable(str(error)) from error
        return None if secret is None else secret.reveal()


def _credential(settings: Settings, name: str) -> str | None:
    try:
        secret = settings.secret(credential_key(name))
    except ConfigurationError as error:
        raise NotRunnable(str(error)) from error
    return None if secret is None else secret.reveal()


def _family(name: str) -> Family:
    if name == "worker":
        return "worker"
    if name == "connector":
        return "connector"
    return "model"


def _json(path: str | None, setting: str) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        with Path(path).open(encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as error:
        raise NotRunnable(f"{setting}: the file cannot be read as JSON: {error}") from error
    if not isinstance(document, dict):
        raise NotRunnable(f"{setting}: the file holds no JSON object")
    return document
