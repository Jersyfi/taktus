<!--
	One model trial (#448, ADR-0149): per candidate the cases passed, money, tokens in and out and
	wall time, each charted on one axis from zero, and each case's results beside the other
	candidates'. The report decides nothing: binding a model to a purpose stays a person's act.
-->
<script lang="ts">
	import { runLink } from './links';
	import OperationPage from './OperationPage.svelte';
	import StepBars from './StepBars.svelte';
	import { count, money, occasion, trialSentence, trialsLink, type Row, type TrialRead } from './spend';

	let { read }: { read: TrialRead } = $props();

	const candidates = $derived(read.report.candidates ?? []);
	const differing = $derived(new Set(read.report.differing ?? []));
	const sentence = $derived(trialSentence(read));
	function bars(figure: (c: (typeof candidates)[number]) => number, label: (n: number) => string): Row[] {
		const most = Math.max(0, ...candidates.map(figure));
		return candidates.map((c) => ({
			step: c.model,
			bars: [{ series: 0, share: most > 0 ? figure(c) / most : 0, label: label(figure(c)) }]
		}));
	}
	const cases = $derived(read.trial.cases ?? []);
	const lines = $derived([
		...candidates.map(
			(c) =>
				`${c.model}: ${c.passed ?? 0} of ${cases.length} passed, ${money(c.amount, c.currency)}, ${count(c.tokens_in ?? 0)} tokens in, ${count(c.tokens_out ?? 0)} out, ${(c.wall_seconds ?? 0).toFixed(1)} s.`
		),
		...[...differing].map((c) => `The results of ${c} differ between the candidates.`),
		...Object.entries(read.trial.left_out ?? {}).map(([c, why]) => `Left out: ${c}, ${why}.`)
	]);
	function outcomeOf(model: string, key: string) {
		return candidates.find((c) => c.model === model)?.cases?.find((o) => o.case === key);
	}
</script>

<OperationPage eyebrow="Model trial · {read.trial.purpose}" {sentence} {lines}>
	<p class="meta">
		{occasion(read.trial.occasion)} · started {new Date(read.trial.started_at).toLocaleString('en')} ·
		<a href={trialsLink()}>every trial</a>
	</p>
	<StepBars title="Money per candidate" rows={bars((c) => c.amount ?? 0, (n) => money(n, candidates[0]?.currency))} />
	<StepBars title="Tokens in and out per candidate" rows={bars((c) => (c.tokens_in ?? 0) + (c.tokens_out ?? 0), (n) => `${count(n)} tokens`)} />
	<StepBars title="Wall time per candidate" rows={bars((c) => c.wall_seconds ?? 0, (n) => `${n.toFixed(1)} s`)} />
	<table>
		<thead>
			<tr>
				<th scope="col">Case</th>
				{#each candidates as c (c.model)}<th scope="col">{c.model}</th>{/each}
			</tr>
		</thead>
		<tbody>
			{#each cases as item (item.key)}
				<tr class:differs={differing.has(item.key)}>
					<th scope="row">{item.key}{#if differing.has(item.key)}<span class="mark look">results differ</span>{/if}</th>
					{#each candidates as c (c.model)}
						{@const outcome = outcomeOf(c.model, item.key)}
						<td>
							{#if outcome}
								<a href={runLink(outcome.run_id)}>{outcome.passed ? 'passed' : (outcome.state ?? 'running')}</a>
								<span class="meta">{money(outcome.amount, c.currency)}</span>
								{#each Object.entries(outcome.results ?? {}) as [step, digest] (step)}
									<code title={digest}>{step}: {digest.slice(7, 15)}</code>
								{/each}
							{:else}-{/if}
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
	<p class="meta">Binding a model to {read.trial.purpose} stays your act; this trial changed nothing.</p>
</OperationPage>

<style>
	table {
		border-collapse: collapse;
		font-size: 0.85rem;
		width: 100%;
		max-width: 52rem;
		margin-bottom: 1rem;
	}
	th,
	td {
		text-align: left;
		vertical-align: top;
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid var(--line);
	}
	td {
		display: table-cell;
	}
	td code {
		display: block;
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--ink-2);
	}
	tbody th {
		font-family: var(--mono);
		font-weight: 400;
	}
	tbody th .mark {
		display: flex;
		margin-top: 0.25rem;
	}
</style>
