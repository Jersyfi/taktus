<!--
	Two runs of the same task side by side, step by step (#449, ADR-0148): each run's money and
	tokens on one shared axis, so that the lengths compare, and per step the difference and
	whether both produced the same result. A change is adopted only when this shows it better.
	Where the runs are of different processes or priced at different tables, the page says so.
-->
<script lang="ts">
	import { runLink } from './links';
	import OperationPage from './OperationPage.svelte';
	import StepBars from './StepBars.svelte';
	import {
		comparisonSentence,
		count,
		money,
		moneyBars,
		mostMoney,
		mostTokens,
		rows,
		signed,
		spendLink,
		tokenBars,
		type RunComparison
	} from './spend';

	let { compared }: { compared: RunComparison } = $props();

	const left = $derived(compared.left);
	const right = $derived(compared.right);
	const series = $derived([left.run_id, right.run_id]);
	const sentence = $derived(comparisonSentence(compared));
	const byMoney = $derived(mostMoney(left.steps, right.steps));
	const byTokens = $derived(mostTokens(left.steps, right.steps));
	const RESULT = (same: boolean | null | undefined) =>
		same === true ? 'same result' : same === false ? 'different result' : 'no result to compare';
	const lines = $derived([
		...(compared.comparable ?? []).map((c) => `Caveat: ${c}.`),
		...compared.steps.map(
			(d) =>
				`${d.step_id}: ${signed(d.amount, right.currency)}, ${d.tokens_in ?? 0} tokens in, ${d.tokens_out ?? 0} out, ${d.turns ?? 0} turns, ${RESULT(d.same_result)}.`
		),
		`In all: ${money(left.amount, left.currency)} against ${money(right.amount, right.currency)}.`
	]);
</script>

<OperationPage eyebrow="Two runs side by side" {sentence} {lines}>
	<p class="meta">
		<a href={runLink(left.run_id)}>{left.run_id}</a> ({money(left.amount, left.currency)}) beside
		<a href={runLink(right.run_id)}>{right.run_id}</a> ({money(right.amount, right.currency)})
		· <a href={spendLink(left.run_id)}>{left.run_id} alone</a>
	</p>
	{#each compared.comparable ?? [] as caveat (caveat)}
		<p class="mark look">{caveat}</p>
	{/each}
	<StepBars
		title="Money per step"
		{series}
		rows={rows(moneyBars(left.steps, left.currency, byMoney), moneyBars(right.steps, right.currency, byMoney))}
	/>
	<StepBars
		title="Tokens per step"
		{series}
		rows={rows(tokenBars(left.steps, byTokens), tokenBars(right.steps, byTokens))}
	/>
	<table>
		<thead>
			<tr><th scope="col">Step</th><th scope="col">Money, right less left</th><th scope="col">Tokens in</th><th scope="col">Tokens out</th><th scope="col">Turns</th><th scope="col">Result</th></tr>
		</thead>
		<tbody>
			{#each compared.steps as d (d.step_id)}
				<tr class:differs={d.same_result === false}>
					<th scope="row">{d.step_id}</th>
					<td>{signed(d.amount, right.currency)}</td>
					<td>{d.tokens_in === null || d.tokens_in === undefined ? '-' : count(d.tokens_in)}</td>
					<td>{d.tokens_out === null || d.tokens_out === undefined ? '-' : count(d.tokens_out)}</td>
					<td>{d.turns ?? '-'}</td>
					<td>{RESULT(d.same_result)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</OperationPage>

<style>
	table {
		border-collapse: collapse;
		font-size: 0.85rem;
		max-width: 52rem;
		width: 100%;
	}
	th,
	td {
		text-align: left;
		padding: 0.35rem 0.6rem;
		border-bottom: 1px solid var(--line);
	}
	thead th {
		color: var(--ink-2);
		font-weight: 500;
	}
	tbody th {
		font-family: var(--mono);
		font-weight: 400;
	}
	tr.differs td:last-child {
		font-weight: 600;
	}
</style>
