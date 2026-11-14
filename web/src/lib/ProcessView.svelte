<!--
	The process level of UC-6.10: the steps of one process version as a graph, each showing how it
	works, with the autonomy statement — the level the process runs at, and why (ADR-0026). A step
	moves only while a run of the version runs it. The newest runs of the version lead down to their
	run level, the rest to the list of runs narrowed to the process; the versions lead to their own
	graphs (ADR-0064, ADR-0321 §2). The drawing is shown first and its text equivalent on a switch
	(ADR-0322): the runs are a list, so each run's text stands in its own row and nowhere else.
-->
<script lang="ts">
	import DisplaySwitch from './DisplaySwitch.svelte';
	import ExactnessStatement from './ExactnessStatement.svelte';
	import Glyph from './Glyph.svelte';
	import Graph from './Graph.svelte';
	import TextEquivalent from './TextEquivalent.svelte';
	import { display, type Display } from './display.svelte';
	import { chosen } from './motion.svelte';
	import { changeLink, processLink, runLink, variantsLink } from './links';
	import { when } from './runs';
	import { processSpendLink } from './spend';
	import type { ProcessLevel } from './types';

	/** How many of the version's runs the page lists; the rest are on the list of runs. */
	const NEWEST = 10;

	let { level, motionAllowed, mode }: { level: ProcessLevel; motionAllowed: boolean; mode?: Display } = $props();

	const shown = $derived(mode ?? display.of('process'));
	const process = $derived(level.process);
	const runs = $derived(level.runs ?? []);
	const newest = $derived(runs.slice(0, NEWEST));
	/** Every run of the version by state, as the surface counted them (ADR-0319 §3). */
	const counted = $derived(Object.entries(level.counts ?? {}).filter(([, n]) => n > 0));
	const total = $derived(level.counts ? counted.reduce((n, [, c]) => n + c, 0) : runs.length);
	const byId = $derived(new Map(level.steps.map((s) => [s.id, s])));

	function notes(id: string): string[] {
		const step = byId.get(id);
		if (!step) return [];
		const found = [step.method + (step.exactness ? ` · ${step.exactness}` : '')];
		// Who acts at a person's step: a role, never a person (ADR-0146).
		if (step.role) found.push(`role ${step.role}`);
		else if (step.fallback_role) found.push(`falls back to ${step.fallback_role}`);
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
			· <a href={variantsLink(process.id)}>how it really runs</a>
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

	<div class="tools"><DisplaySwitch page="process" /></div>

	{#if shown === 'picture'}
		<Graph steps={level.steps} {motionAllowed} {notes} />
	{/if}
	<TextEquivalent label="The process as text" mode={shown}>
		<li data-text="summary">{level.summary}</li>
		<li data-text="process">{process.text}</li>
		{#each level.steps as step (step.id)}
			<li data-text={step.id}>{step.text}</li>
		{/each}
	</TextEquivalent>

	{#if level.exactness}
		<ExactnessStatement statement={level.exactness} />
	{/if}

	<section class="runs" aria-labelledby="runs-title">
		<h2 id="runs-title">Runs of this version</h2>
		{#if counted.length}
			<p class="counted" data-counts>{total} in all: {counted.map(([state, n]) => `${n} ${state.replace('_', ' ')}`).join(', ')}.</p>
		{/if}
		{#if runs.length === 0}
			<p>No run you may see.</p>
		{:else}
			<ul data-runs-of-version>
				{#each newest as run (run.id)}
					<li data-text="run:{run.id}">
						<Glyph glyph={chosen(run.drawn, motionAllowed)} size={22} />
						<a href={runLink(run.id)}>{run.id}</a>
						<span class="state">{run.state.replace('_', ' ')}</span>
						<time datetime={run.created_at}>{when(run.created_at)}</time>
						<span class="said" class:sr-only={shown === 'picture'}>{run.text}</span>
					</li>
				{/each}
			</ul>
			{#if total > newest.length || level.next}
				<p><a href="#/runs?process={encodeURIComponent(process.id)}">Every run of {process.name}</a></p>
			{/if}
		{/if}
	</section>
</section>

<style>
	.meta {
		margin: var(--sp-025) 0 0;
		color: var(--text-secondary);
	}
	.version {
		margin-inline-end: var(--sp-050);
	}
	.autonomy {
		margin: var(--sp-200) 0 var(--sp-300);
		padding: var(--sp-150) var(--sp-200);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-radius: var(--r-lg);
		max-width: 56rem;
		color: var(--text-secondary);
	}
	.autonomy p {
		margin: var(--sp-025) 0;
	}
	.level {
		font-weight: var(--fw-semibold);
	}
	.tools {
		display: flex;
		justify-content: flex-end;
	}
	.runs ul {
		list-style: none;
		padding: 0;
	}
	.runs li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-100);
		align-items: center;
		padding: var(--sp-050) 0;
	}
	.state,
	.counted {
		color: var(--text-secondary);
	}
	time {
		font-size: var(--fs-090);
		color: var(--text-subtle);
	}
	.said {
		flex-basis: 100%;
		font-size: var(--fs-090);
		color: var(--text-secondary);
	}
</style>
