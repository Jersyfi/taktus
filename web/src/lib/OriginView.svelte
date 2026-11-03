<!--
	The origin of a result, the fourth level of UC-6.10: the path from a result back through the
	steps and sources that produced it, drawn from the provenance records (ADR-0021, ADR-0068).
	Read from left to right it runs from what was read to what was produced; nothing moves, for a
	past result is drawn as it was recorded. Each step on the path leads to its run. Written out
	below as its text equivalent.
-->
<script lang="ts">
	import Graph from './Graph.svelte';
	import { runLink, wrongResultLink } from './links';
	import type { OriginLevel } from './types';

	let { level, motionAllowed }: { level: OriginLevel; motionAllowed: boolean } = $props();

	const sources = $derived(level.sources ?? []);
	// Sources first, then the steps from the earliest read to the producing step, then the result.
	const nodes = $derived([
		...sources.map((s) => ({ id: s.id, name: 'source', drawn: s.drawn })),
		...[...level.steps]
			.reverse()
			.map((s) => ({ id: s.id, name: s.step, depends_on: s.depends_on, drawn: s.drawn })),
		{ id: level.result.id, name: 'result', depends_on: level.result.depends_on, drawn: level.result.drawn }
	]);
	const labels = $derived(
		new Map<string, string[]>([
			...sources.map((s) => [s.id, [s.capability, s.ref]] as [string, string[]]),
			...level.steps.map(
				(s) => [s.id, [`${s.method}${s.exactness ? ` · ${s.exactness}` : ''}`, s.run]] as [string, string[]]
			),
			[level.result.id, [level.result.exactness]]
		])
	);
	const runs = $derived([...new Set(level.steps.map((s) => s.run))]);
</script>

<section class="origin" aria-labelledby="origin-title">
	<p class="eyebrow">Where the result of {level.result.step} came from</p>
	<h1 id="origin-title">{level.summary}</h1>
	<p class="meta">
		Run <a href={runLink(level.result.run)}>{level.result.run}</a> · {level.result.exactness}
		· <a href={wrongResultLink(level.result.run, level.result.step)}>if it was wrong, where it went</a>
	</p>

	<Graph steps={nodes} {motionAllowed} notes={(id) => labels.get(id) ?? []} />

	{#if runs.length > 1}
		<p class="meta">
			Across runs:
			{#each runs as run (run)}<a class="run" href={runLink(run)}>{run}</a>{/each}
		</p>
	{/if}

	<section class="text" aria-label="The origin as text">
		<h2>As text</h2>
		<ol>
			<li data-text="summary">{level.summary}</li>
			<li data-text="result">{level.result.text}</li>
			{#each level.steps as step (step.id)}
				<li data-text={step.id}>{step.text}</li>
			{/each}
			{#each sources as source (source.id)}
				<li data-text={source.id}>{source.text}</li>
			{/each}
		</ol>
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
	.meta {
		color: var(--muted);
		margin: 0.2rem 0 1rem;
	}
	a {
		color: inherit;
	}
	.run {
		margin-left: 0.4rem;
	}
</style>
