<!--
	The model trials (#448, ADR-0149): the trials offered now, each startable with the candidates
	it names, a trial started by hand, and every trial of the tenant. A trial is offered, never
	started on its own; starting one runs rehearsals and binds no model.
-->
<script lang="ts">
	import OperationPage from './OperationPage.svelte';
	import { occasion, offerLine, trialsLink, type Offer, type Trials } from './spend';

	let {
		trials,
		onStart,
		problem = null
	}: {
		trials: Trials;
		onStart: (purpose: string, candidates: string[], occasion: string) => void;
		problem?: string | null;
	} = $props();

	let purpose = $state('');
	let candidates = $state('');
	const offered = $derived(trials.offers.length);
	const sentence = $derived(
		offered === 0
			? `No trial is offered now; ${trials.trials.length} ${trials.trials.length === 1 ? 'trial was' : 'trials were'} run.`
			: `${offered} ${offered === 1 ? 'trial is' : 'trials are'} offered; ${trials.trials.length} ${trials.trials.length === 1 ? 'was' : 'were'} run.`
	);
	const lines = $derived([
		...trials.offers.map(offerLine),
		...trials.trials.map((t) => `${t.id}: ${t.purpose}, ${t.candidates.join(', ')}, ${occasion(t.occasion)}.`)
	]);
	function start(offer: Offer) {
		onStart(offer.purpose, offer.candidates, offer.occasion);
	}
</script>

<OperationPage eyebrow="Model trials" {sentence} {lines}>
	{#if problem}<p class="mark look" role="alert">{problem}</p>{/if}
	{#if trials.offers.length > 0}
		<h2>Offered</h2>
		<ul class="records">
			{#each trials.offers as offer (offer.purpose + offer.occasion + offer.model)}
				<li class="record">
					<p class="mark">{occasion(offer.occasion)}</p>
					<h3>{offer.purpose}</h3>
					<p class="meta">{offer.reason}</p>
					<p class="meta">Compares {offer.candidates.join(', ')}</p>
					<button type="button" onclick={() => start(offer)} disabled={offer.candidates.length === 0}>Run the trial</button>
				</li>
			{/each}
		</ul>
	{/if}
	<h2>Run a trial</h2>
	<form
		class="start"
		onsubmit={(event) => {
			event.preventDefault();
			const named = candidates.split(/[\s,]+/).filter(Boolean);
			if (purpose.trim() && named.length > 0) onStart(purpose.trim(), named, 'asked');
		}}
	>
		<label>Purpose <input bind:value={purpose} placeholder="drafting" autocomplete="off" /></label>
		<label>Candidates <input bind:value={candidates} placeholder="model.a, model.b" autocomplete="off" /></label>
		<button type="submit" disabled={!purpose.trim() || !candidates.trim()}>Run the trial</button>
	</form>
	<p class="meta">Every evaluation case of the processes that ask for the purpose runs once per candidate, as a rehearsal. Nothing outside is acted on, and no model is bound.</p>
	<h2>Run</h2>
	{#if trials.trials.length === 0}
		<p class="empty">No trial yet.</p>
	{:else}
		<ul class="records">
			{#each trials.trials as trial (trial.id)}
				<li class="record">
					<p class="mark">{occasion(trial.occasion)}</p>
					<h3><a href={trialsLink(trial.id)}>{trial.purpose}</a></h3>
					<p class="meta">{trial.candidates.join(', ')}</p>
					<p class="id">{trial.id} · {new Date(trial.started_at).toLocaleString('en')}</p>
				</li>
			{/each}
		</ul>
	{/if}
</OperationPage>

<style>
	.start {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: end;
	}
	label {
		display: grid;
		gap: 0.25rem;
		font-size: 0.85rem;
		color: var(--ink-2);
	}
	input {
		font: inherit;
		font-family: var(--mono);
		padding: 0.35rem 0.6rem;
		border: 1px solid var(--line);
		border-radius: 8px;
		background: var(--paper);
		color: var(--ink);
	}
	button {
		font: inherit;
		padding: 0.35rem 0.9rem;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: var(--paper);
		color: var(--ink);
		cursor: pointer;
		margin-top: 0.4rem;
	}
</style>
