<!--
	Changing a process in dialogue, and rolling it back (UC-4.15, ADR-0091 §6). The person asks for
	a change in their own words; S-07 turns it into a proposal. Each proposal is shown as its
	difference, step by step, with each changed step's method, reason and class before and after —
	in words, because a proposal is not a level and `reporting` hands no glyph for it. A proposal
	is rehearsed, then commissioned or discarded; the rehearsal's result is shown with it, read from
	the rehearsal's run, and commissioning is offered once that run has finished. The versions are listed, each earlier one with a
	rollback. The page sends what the person chose and shows what the surface answers; it decides
	nothing, and computes nothing.
-->
<script lang="ts">
	import { processLink, runLink } from './links';
	import type { ProcessLevel, Proposal, RunLevel, StepChange } from './types';

	let {
		level,
		proposals,
		rehearsals = {},
		busy = false,
		message = null,
		onAsk,
		onRehearse,
		onCommission,
		onDiscard,
		onRollback
	}: {
		level: ProcessLevel;
		proposals: Proposal[];
		/** The run level of each proposal's rehearsal, by proposal; absent where it cannot be read. */
		rehearsals?: Record<string, RunLevel>;
		busy?: boolean;
		message?: string | null;
		onAsk: (request: string) => void;
		onRehearse: (proposal: string) => void;
		onCommission: (proposal: string) => void;
		onDiscard: (proposal: string) => void;
		onRollback: (version: string) => void;
	} = $props();

	const process = $derived(level.process);
	const active = $derived(process.versions.find((v) => v.active)?.version);
	const open = $derived(proposals.filter((p) => p.state === 'proposed' || p.state === 'rehearsed'));
	let request = $state('');

	function ask(event: SubmitEvent) {
		event.preventDefault();
		if (request.trim()) onAsk(request.trim());
		request = '';
	}

	/** The rehearsal ended well: only then is commissioning offered (ADR-0091 §4). */
	const finished = (proposal: Proposal) => rehearsals[proposal.id]?.run.state === 'finished';

	function how(step: StepChange['after']): string {
		if (!step) return '';
		return `${step.method}${step.exactness ? ` · ${step.exactness}` : ''} — ${step.reason}`;
	}
</script>

<section class="change" aria-labelledby="change-title">
	<p class="eyebrow"><a href={processLink(process.id)}>{process.name}</a> · change in dialogue</p>
	<h1 id="change-title">
		{open.length === 0
			? 'Say what should change.'
			: `${open.length} ${open.length === 1 ? 'proposal waits' : 'proposals wait'} for you.`}
	</h1>
	<p class="muted">Nothing changes until you commission a rehearsed proposal. Every version stays.</p>

	<form class="ask" onsubmit={ask}>
		<label>
			What should change, in your own words
			<textarea rows="3" bind:value={request}></textarea>
		</label>
		<button type="submit" disabled={busy || !request.trim()}>Ask Taktus</button>
	</form>
	{#if message}<p class="message" aria-live="polite">{message}</p>{/if}

	{#each open as proposal (proposal.id)}
		<article class="proposal" data-proposal={proposal.id}>
			<header>
				<strong>Version {proposal.version}</strong>, against {proposal.base_version}
				<span class="state" data-state={proposal.state}>{proposal.state}</span>
			</header>
			{#if proposal.request}<p class="request">“{proposal.request}”</p>{/if}
			<ul class="difference">
				{#each proposal.difference.steps ?? [] as step (step.id)}
					<li data-change={step.change}>
						<span class="kind">{step.change}</span>
						<strong>{step.id}</strong>
						{#if step.change === 'changed'}
							<span class="muted">({(step.fields ?? []).join(', ')})</span>
							<div class="was">was: {how(step.before)}</div>
							<div>now: {how(step.after)}</div>
						{:else if step.change === 'added'}
							<div>{how(step.after)}</div>
						{:else}
							<div class="was">{how(step.before)}</div>
						{/if}
					</li>
				{/each}
				{#if proposal.difference.triggers_changed}<li data-change="triggers">its triggers change</li>{/if}
				{#if proposal.difference.inputs_changed}<li data-change="inputs">its inputs change</li>{/if}
			</ul>
			{#if proposal.state === 'proposed'}
				<p class="muted">
					Not rehearsed yet. A rehearsal runs this version and acts on nothing outside; every outward
					step answers from the recording of its last real call.
				</p>
			{/if}
			{#if proposal.rehearsal_run}
				{@const seen = rehearsals[proposal.id]}
				<section class="rehearsal" data-rehearsal={proposal.rehearsal_run} aria-label="Rehearsal">
					<p>
						<strong>A rehearsal</strong>, run
						<a href={runLink(proposal.rehearsal_run)}>{proposal.rehearsal_run}</a>:
						nothing left the system.
					</p>
					{#if seen}
						<p data-run-state={seen.run.state}>{seen.summary}</p>
						<ul>
							{#each seen.steps as step (step.id)}
								<li data-step-state={step.state}>
									<span class="kind">{step.state}</span> <strong>{step.id}</strong>
									<span class="muted">{step.method}</span>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="muted">The rehearsal cannot be read yet.</p>
					{/if}
				</section>
			{/if}
			<div class="row">
				<button type="button" disabled={busy} onclick={() => onRehearse(proposal.id)}>
					{proposal.state === 'rehearsed' ? 'Rehearse again' : 'Rehearse'}
				</button>
				{#if proposal.state === 'rehearsed' && finished(proposal)}
					<button type="button" class="primary" disabled={busy} onclick={() => onCommission(proposal.id)}>
						Commission version {proposal.version}
					</button>
				{/if}
				<button type="button" disabled={busy} onclick={() => onDiscard(proposal.id)}>Discard</button>
			</div>
		</article>
	{/each}

	<section class="versions" aria-label="Versions">
		<h2>Versions — and how to go back</h2>
		<ul>
			{#each [...process.versions].reverse() as v (v.version)}
				<li>
					<span class="v">{v.version}</span>
					<span>{v.active ? 'active' : 'registered'}</span>
					{#if v.version !== active}
						<button type="button" disabled={busy} onclick={() => onRollback(v.version)}>Roll back to {v.version}</button>
					{/if}
				</li>
			{/each}
		</ul>
		<p class="muted">
			Rolling back registers the earlier content again as a new version, which becomes active. Nothing is
			deleted; a run under way finishes on its version.
		</p>
	</section>
</section>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.85rem;
	}
	.ask {
		display: grid;
		gap: 0.5rem;
		max-width: 46rem;
		margin: 1.25rem 0;
	}
	.ask label {
		display: grid;
		gap: 0.3rem;
	}
	textarea {
		font: inherit;
		padding: 0.6rem 0.8rem;
		border: 1px solid var(--line);
		border-radius: 12px;
		background: var(--paper);
		color: var(--ink);
	}
	.proposal {
		border: 1px solid var(--line);
		border-radius: 18px;
		padding: 1rem 1.2rem;
		margin: 1rem 0;
		max-width: 52rem;
	}
	.state {
		font-family: var(--mono);
		font-size: 0.72rem;
		border: 1px solid var(--line);
		border-radius: 6px;
		padding: 0 0.35rem;
		margin-left: 0.5rem;
	}
	.request {
		font-family: var(--serif);
		font-size: 1.1rem;
	}
	.difference {
		list-style: none;
		padding: 0;
		display: grid;
		gap: 0.5rem;
	}
	.difference li {
		padding: 0.5rem 0.75rem;
		border-radius: 10px;
		background: var(--paper-2);
	}
	.kind {
		font-family: var(--mono);
		font-size: 0.72rem;
		text-transform: uppercase;
		margin-right: 0.4rem;
		color: var(--ink-2);
	}
	.rehearsal {
		border-left: 3px solid var(--line);
		padding: 0.1rem 0.9rem;
		margin: 0.75rem 0;
	}
	.rehearsal ul {
		list-style: none;
		padding: 0;
		margin: 0 0 0.5rem;
	}
	.was {
		color: var(--ink-3);
		text-decoration: line-through;
	}
	.row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	button {
		font: inherit;
		border: 1px solid var(--line);
		background: var(--paper);
		color: var(--ink);
		border-radius: 10px;
		padding: 0.4rem 0.9rem;
		cursor: pointer;
	}
	button.primary {
		background: var(--ink);
		color: var(--paper);
		border-color: var(--ink);
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.versions ul {
		list-style: none;
		padding: 0;
		max-width: 40rem;
	}
	.versions li {
		display: flex;
		gap: 1rem;
		align-items: center;
		padding: 0.4rem 0;
		border-bottom: 1px solid var(--line);
	}
	.versions button {
		margin-left: auto;
	}
	.v {
		font-family: var(--mono);
	}
	.message {
		background: var(--paper-2);
		border-radius: 12px;
		padding: 0.7rem 0.9rem;
		max-width: 46rem;
	}
</style>
