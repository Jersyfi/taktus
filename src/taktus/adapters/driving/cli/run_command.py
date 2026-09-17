"""`taktusctl run`: a process bundle runs against one worker endpoint; the ledger and the
provenance are shown.

The one execution path of control-plane.md §1, driven from the command line: the invocation
becomes a Command on the `channel.cli` capability, the bundle becomes a process version, the
command becomes a commissioned plan, the plan runs. `--resume` continues a halted run at its
step boundary; the bundle is read again, so that a changed `limits` block is a changed budget.
`--stop-after N` requests a stop after N steps have finished, at the boundary.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.command.application.service import CommissionPlan
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.run.application.query import ProvenanceOfRun
from taktus.components.run.application.service import ResumeRun, StartRun
from taktus.components.run.domain.model import Run, RunError, RunState
from taktus.components.run.domain.service.provenance import ChainVerification
from taktus.ports.ledger import Verification
from taktus.ports.worker import Limits, WorkerError
from taktus.shared.v1 import Command, ConsumptionQuantities, Intent, LedgerEntry, ReplyTo

DEFAULT_WORKER = "http://127.0.0.1:9000"
DEFAULT_STATE_DIR = "~/.cache/taktus/taktusctl"
DEFAULT_TENANT = "default"


def run(
    ctx: typer.Context,
    process: Annotated[Path, typer.Option("--process", help="The process bundle to run (YAML).")],
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume", metavar="RUN_ID", help="Continue this halted run at its boundary."
        ),
    ] = None,
    stop_after: Annotated[
        int | None,
        typer.Option(
            "--stop-after", metavar="N", min=1, help="Stop after N steps, at the boundary."
        ),
    ] = None,
    worker: Annotated[
        str,
        typer.Option(
            "--worker",
            envvar="TAKTUS_WORKER",
            help="Base URL of the running worker that serves the bundle's worker steps.",
        ),
    ] = DEFAULT_WORKER,
    state_dir: Annotated[
        Path,
        typer.Option(
            "--state-dir",
            envvar="TAKTUS_STATE_DIR",
            help="Where runs, plans, the ledger and artifacts are written between invocations "
            "(development only).",
        ),
    ] = Path(DEFAULT_STATE_DIR),
    identity: Annotated[
        str,
        typer.Option(
            "--identity",
            help="The identity the command is attributed to. The CLI channel authenticates "
            "nobody yet; this is an opaque label, not a name.",
        ),
    ] = "idn_local",
    tenant: Annotated[
        str,
        typer.Option(
            "--tenant",
            envvar="TAKTUS_TENANT",
            help="The tenant the run belongs to. Until the identity component exists there is "
            "one, created by the migration.",
        ),
    ] = DEFAULT_TENANT,
) -> None:
    """Run a process bundle against a worker and print the ledger and the consumption.

    Exit code 0: the run finished. Exit code 3: the run halted or escalated; the output says
    why and how to resume. Exit code 2: the bundle or the invocation is wrong.
    """
    wiring: Wiring = ctx.obj
    try:
        bundle = _load(process)
    except (OSError, yaml.YAMLError, ValueError) as error:
        typer.echo(f"cannot read {process}: {error}", err=True)
        raise typer.Exit(code=2) from error
    try:
        result = asyncio.run(
            _run(
                wiring,
                bundle,
                process,
                state_dir=Path(os.path.expanduser(state_dir)),
                worker_endpoint=worker,
                resume=resume,
                stop_after=stop_after,
                identity=identity,
                tenant=tenant,
            )
        )
    except InvalidProcess as error:
        typer.echo(f"{process} is not a valid process:", err=True)
        for finding in error.findings:
            typer.echo(f"  - {finding}", err=True)
        raise typer.Exit(code=2) from error
    except (RunError, WorkerError, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
    raise typer.Exit(code=0 if result.state is RunState.FINISHED else 3)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError("the bundle is not a mapping")
    return document


async def _run(
    wiring: Wiring,
    bundle: dict[str, Any],
    bundle_path: Path,
    *,
    state_dir: Path,
    worker_endpoint: str,
    resume: str | None,
    stop_after: int | None,
    identity: str,
    tenant: str,
) -> Run:
    async with wiring.services(state_dir=state_dir, worker_endpoint=worker_endpoint) as services:
        typer.echo(f"state  {services.storage}")
        version = await services.register_version.execute(
            RegisterProcessVersion(bundle, tenant=tenant)
        )
        budget = _budget(version)
        if resume is None:
            run = await _start(services, version, budget, identity, tenant, stop_after)
        else:
            run = await services.engine.resume(
                ResumeRun(
                    run_id=resume,
                    actor=identity,
                    tenant=tenant,
                    budget=budget,
                    stop_after=stop_after,
                )
            )
        async with services.work.transaction(tenant):
            entries = await services.ledger.entries(tenant, run.id)
            verification = await services.ledger.verify(tenant)
        chain = await services.provenance.verify(ProvenanceOfRun(run_id=run.id, tenant=tenant))
        typer.echo(render(run, version, entries, verification, chain, bundle_path))
        return run


async def _start(
    services: Services,
    version: ProcessVersion,
    budget: Limits,
    identity: str,
    tenant: str,
    stop_after: int | None,
) -> Run:
    now = services.clock.now()
    command = Command(
        id=services.ids.new("cmd"),
        channel="channel.cli",
        identity=identity,
        org_path=(tenant,),
        intent=Intent(raw=f"run {version.ref}", recognised="process.run"),
        reply_to=ReplyTo(channel="channel.cli", address="stdout"),
        received_at=now,
    )
    plan = await services.commission.execute(
        CommissionPlan(
            command=command,
            tenant=tenant,
            goal=f"run process {version.name} ({version.ref})",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    return await services.engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=budget,
            process_version=version.ref,
            actor=identity,
            tenant=tenant,
            stop_after=stop_after,
        )
    )


def _budget(version: ProcessVersion) -> Limits:
    if version.limits is None:
        raise InvalidProcess(
            ("the bundle names no `limits`; a run needs a budget to admit its steps against",)
        )
    try:
        return Limits.model_validate(dict(version.limits))
    except ValueError as error:
        raise InvalidProcess((f"`limits`: {error}",)) from error


# --- output ---------------------------------------------------------------------------------------


def render(
    run: Run,
    version: ProcessVersion,
    entries: Sequence[LedgerEntry],
    verification: Verification,
    chain: ChainVerification,
    bundle_path: Path,
) -> str:
    lines = [f"run {run.id}  process {run.process_version}  state {_state(run)}"]
    if run.reason:
        lines.append(f"  {run.reason}")
    lines.append("")
    lines.append("steps")
    for step_run in run.step_runs:
        step = version.step(step_run.step_id)
        detail = [
            f"{step_run.index + 1:>2}",
            f"{step_run.step_id:<20}",
            f"{step.method:<10}",
            f"{step.exactness or '-':<9}",
            f"{step_run.state:<10}",
        ]
        if step_run.consumption is not None:
            detail.append(_quantities(step_run.consumption))
        if step_run.artifacts:
            detail.append("artifacts: " + ", ".join(a.id for a in step_run.artifacts))
        if step_run.reason and step_run.state not in ("succeeded",):
            detail.append(f"— {step_run.reason}")
        lines.append("  " + " ".join(detail))
    lines.append("")
    lines.append(f"ledger  {len(entries)} entries of this run, chain of {verification.entries}: ")
    lines[-1] += "verifies" if verification.intact else "DOES NOT VERIFY"
    for finding in verification.findings:
        lines.append(f"  ! {finding}")
    for entry in entries:
        columns = [
            f"{entry.seq:>4}",
            entry.ts.strftime("%H:%M:%S"),
            f"{entry.kind:<14}",
            f"{entry.refs.step_id or '':<20}",
            f"{entry.outcome or '':<22}",
            _quantities(entry.consumption) if entry.consumption else "",
            entry.hash[7:19],
        ]
        lines.append("  " + " ".join(columns).rstrip())
    lines.append("")
    lines.append(f"provenance  {chain.records} records of this run, one per completed step: ")
    lines[-1] += "chain verifies" if chain.intact else "chain DOES NOT VERIFY"
    for finding in chain.findings:
        lines.append(f"  ! {finding}")
    lines.append("")
    lines.append("consumption  " + (_quantities(run.consumed()) or "nothing measured"))
    lines.append("budget       " + _limits(run.budget))
    if run.state in (RunState.HALTED, RunState.ESCALATED):
        lines.append("")
        lines.append(
            f"resume with: uv run taktusctl run --process {bundle_path} --resume {run.id}"
            + ("" if run.tenant == DEFAULT_TENANT else f" --tenant {run.tenant}")
        )
    return "\n".join(lines)


def _state(run: Run) -> str:
    return str(run.state) if run.cause is None else f"{run.state} ({run.cause})"


def _quantities(consumption: ConsumptionQuantities) -> str:
    parts = []
    if consumption.tokens_in is not None or consumption.tokens_out is not None:
        parts.append(f"tokens {consumption.tokens_in or 0}/{consumption.tokens_out or 0}")
    for code, amount in (consumption.currency or {}).items():
        parts.append(f"{amount} {code}")
    if consumption.quota_units is not None:
        parts.append(f"quota {consumption.quota_units}")
    if consumption.compute_seconds is not None:
        parts.append(f"compute {consumption.compute_seconds:.3f}s {consumption.resource_class}")
    if consumption.storage_bytes is not None:
        parts.append(f"storage {consumption.storage_bytes}B")
    return ", ".join(parts)


def _limits(limits: Limits) -> str:
    parts = [f"{amount} {code}" for code, amount in (limits.currency or {}).items()]
    if limits.quota is not None:
        parts.append(f"quota {limits.quota.units}")
    if limits.compute is not None:
        parts.append(f"compute {limits.compute.seconds}s {limits.compute.resource_class}")
    return ", ".join(parts)
