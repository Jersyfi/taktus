<!--
	Where one run spent, step by step (#449, ADR-0148): money at the run's own price table, and
	tokens split by price kind, each as a chart on one axis from zero; then every step's figures —
	turns, what a compression saved, Takte — and what could not be priced, said, never shown as
	nothing. From here another run of the same task is set beside it.
-->
<script lang="ts">
	import { processLink, runLink } from './links';
	import OperationPage from './OperationPage.svelte';
	import StepBars from './StepBars.svelte';
	import {
		moneyBars,
		money,
		processSpendLink,
		rows,
		spendLink,
		spendSentence,
		stepLine,
		tokenBars,
		type RunSpend
	} from './spend';

	let { spend }: { spend: RunSpend } = $props();

	let against = $state('');
	const process = $derived(spend.process_version?.split('@')[0] ?? null);
	const sentence = $derived(spendSentence(spend));
	const lines = $derived([
		...spend.steps.map((s) => stepLine(s, spend.currency)),
		...(spend.takte !== null && spend.takte !== undefined ? [`${spend.takte.toFixed(3)} Takte in all, ${spend.calibration}.`] : []),
		...(spend.unpriced ?? []).map((u) => `Not priced: ${u}.`)
	]);
</script>

<OperationPage eyebrow="Spend of a run" {sentence} {lines}>
	<p class="meta">
		<a href={runLink(spend.run_id)}>Run {spend.run_id}</a>
		{#if spend.process_version && process}
			· <a href={processLink(spend.process_version)}>{spend.process_version}</a>
			· <a href={processSpendLink(process)}>the process over 30 days</a>
		{/if}
		{#if spend.table}· price table {spend.table}{/if}
	</p>
	<div class="totals">
		<p><span class="figure">{money(spend.amount, spend.currency)}</span> money</p>
		{#if spend.takte !== null && spend.takte !== undefined}
			<p><span class="figure">{spend.takte.toFixed(2)}</span> Takte, {spend.calibration}</p>
		{/if}
	</div>
	<StepBars title="Money per step" rows={rows(moneyBars(spend.steps, spend.currency))} />
	<StepBars title="Tokens per step, by price kind" rows={rows(tokenBars(spend.steps))} kinds />
	{#if (spend.unpriced ?? []).length > 0}
		<ul class="unpriced">
			{#each spend.unpriced ?? [] as why (why)}<li>Not priced: {why}</li>{/each}
		</ul>
	{/if}
	<form
		class="against"
		onsubmit={(event) => {
			event.preventDefault();
			if (against.trim()) location.hash = spendLink(spend.run_id, against.trim());
		}}
	>
		<label for="against">Set another run of the same task beside it</label>
		<input id="against" bind:value={against} placeholder="run identifier" autocomplete="off" />
		<button type="submit" disabled={!against.trim()}>Compare</button>
	</form>
</OperationPage>

<style>
	.totals {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 2.5rem;
		margin: 0 0 2rem;
	}
	.totals p {
		margin: 0;
		color: var(--ink-2);
	}
	.figure {
		display: block;
		font-family: var(--serif);
		font-size: 2rem;
		color: var(--ink);
	}
	.unpriced {
		color: var(--ink-2);
		font-size: 0.85rem;
	}
	.against {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
		margin-top: 1.5rem;
	}
	.against label {
		flex-basis: 100%;
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
		background: var(--paper-2);
		color: var(--ink);
		cursor: pointer;
	}
</style>
