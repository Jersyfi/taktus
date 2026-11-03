<!--
	Where a process spent over a window, step by step (#449, ADR-0148): every run whose steps
	finished in it, each priced at its own table, the money summed per currency. The reader
	chooses the window; the steps' figures are charts on one axis from zero.
-->
<script lang="ts">
	import { processLink } from './links';
	import OperationPage from './OperationPage.svelte';
	import StepBars from './StepBars.svelte';
	import { moneyBars, money, processSentence, rows, stepLine, tokenBars, type ProcessSpend } from './spend';

	let { spend, days, onDays }: { spend: ProcessSpend; days: number; onDays: (days: number) => void } = $props();

	const currencies = $derived(Object.keys(spend.amounts ?? {}));
	const currency = $derived(currencies.length === 1 ? currencies[0] : null);
	const sentence = $derived(processSentence(spend));
	const lines = $derived([
		...spend.steps.map((s) => stepLine(s, currency)),
		...(spend.unpriced ?? []).map((u) => `Not priced: ${u}.`)
	]);
</script>

<OperationPage eyebrow="Spend of a process" {sentence} {lines}>
	<p class="meta">
		<a href={processLink(spend.process_id)}>{spend.process_id}</a>
		· over the last
		{#each [7, 30, 90] as choice (choice)}
			<button type="button" class="window" aria-pressed={days === choice} onclick={() => onDays(choice)}>{choice} days</button>
		{/each}
	</p>
	{#if spend.runs === 0}
		<p class="empty">No run of {spend.process_id} finished a step in the last {days} days.</p>
	{:else}
		<p class="meta">{Object.entries(spend.amounts ?? {}).map(([c, a]) => money(a, c)).join(' and ') || 'Nothing could be priced.'}</p>
		<StepBars title="Money per step" rows={rows(moneyBars(spend.steps, currency))} />
		<StepBars title="Tokens per step, by price kind" rows={rows(tokenBars(spend.steps))} kinds />
	{/if}
</OperationPage>

<style>
	.window {
		font: inherit;
		font-size: 0.85rem;
		padding: 0.1rem 0.6rem;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: transparent;
		color: var(--ink);
		cursor: pointer;
	}
	.window[aria-pressed='true'] {
		background: var(--ink);
		color: var(--paper);
	}
</style>
