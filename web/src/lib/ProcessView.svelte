<!--
	The process level of UC-6.10: the steps of one process version as a graph, each showing how it
	works, with the autonomy statement — the level the process runs at, and why (ADR-0026). A step
	moves only while a run of the version runs it. The runs of the version lead down to their run
	level, the versions to their own graphs. Written out below the drawing as its text equivalent
	(ADR-0064).
-->
<script lang="ts">
	import Glyph from './Glyph.svelte';
	import Graph from './Graph.svelte';
	import { chosen } from './motion.svelte';
	import { changeLink, processLink, runLink } from './links';
	import { processSpendLink } from './spend';
	import type { ProcessLevel } from './types';

	let { level, motionAllowed }: { level: ProcessLevel; motionAllowed: boolean } = $props();

	const process = $derived(level.process);
	const runs = $derived(level.runs ?? []);
	const byId = $derived(new Map(level.steps.map((s) => [s.id, s])));

	function notes(id: string): string[] {
		const step = byId.get(id);
		if (!step) return [];
		const found = [step.method + (step.exactness ? ` · ${step.exactness}` : '')];
		if (step.running_in?.length) found.push(`running in ${step.running_in.length}`);
		return found;
	}
</script>

<section class="process" aria-labelledby="process-title">
	<header>
		<p class="eyebrow">{process.name}</p>
		<h1 id="process-title">{level.summary}</h1>
		<p class="meta">
			{process.id}@{process.version} · <a href={changeLink(process.id)}>change in dialogue</a>
			· <a href={processSpendLink(process.id)}>where it spends</a>
			{#if process.versions.length > 1}
				· versions:
				{#each process.versions as v (v.version)}
					{@const label = v.active ? `${v.version} (active)` : v.version}
					<a
						class="version"
						href={processLink(`${process.id}@${v.version}`)}
						aria-current={v.version === process.version ? 'page' : undefined}>{label}</a>
				{/each}
			{/if}
		</p>
	</header>

	<section class="autonomy" aria-label="Autonomy statement" data-autonomy-level={process.autonomy.level}>
		<p class="level">Autonomy level {process.autonomy.level}</p>
		<p>{process.autonomy_text}</p>
	</section>

	<Graph steps={level.steps} {motionAllowed} {notes} />

	<section class="runs" aria-labelledby="runs-title">
		<h2 id="runs-title">Runs of this version</h2>
		{#if runs.length === 0}
			<p>No run you may see.</p>
		{:else}
			<ul>
				{#each runs as run (run.id)}
					<li>
						<Glyph glyph={chosen(run.drawn, motionAllowed)} size={22} />
						<a href={runLink(run.id)}>{run.id}</a>
						<span class="state">{run.state.replace('_', ' ')}</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="text" aria-label="The process as text">
		<h2>As text</h2>
		<ol>
			<li data-text="summary">{level.summary}</li>
			<li data-text="process">{process.text}</li>
			{#each level.steps as step (step.id)}
				<li data-text={step.id}>{step.text}</li>
			{/each}
			{#each runs as run (run.id)}
				<li data-text="run:{run.id}">{run.text}</li>
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
		margin: 0.15rem 0 0;
		opacity: 0.75;
	}
	a {
		color: inherit;
	}
	.version {
		margin-right: 0.4rem;
	}
	.autonomy {
		margin: 1rem 0 1.5rem;
		padding: 0.9rem 1.1rem;
		border: 1px solid var(--line);
		border-radius: 14px;
		max-width: 56rem;
		color: var(--ink-2);
	}
	.autonomy p {
		margin: 0.2rem 0;
	}
	.level {
		font-weight: 600;
	}
	.runs ul {
		list-style: none;
		padding: 0;
	}
	.runs li {
		display: flex;
		gap: 0.6rem;
		align-items: center;
		padding: 0.2rem 0;
	}
	.state {
		color: var(--muted);
	}
</style>
