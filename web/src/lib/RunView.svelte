<!--
	The run level of UC-6.10: where one run stands. Drawn from the level the surface hands over
	and from nothing else: every glyph is the vocabulary's, picked with motion or without by the
	reader's setting, and every figure is the run component's. The same states and figures are
	written out below the drawing, as its text equivalent. It leads to its process (ADR-0064).
-->
<script lang="ts">
	import ExactnessStatement from './ExactnessStatement.svelte';
	import Glyph from './Glyph.svelte';
	import Graph from './Graph.svelte';
	import { chosen } from './motion.svelte';
	import { originLink, processLink, requestsLink } from './links';
	import type { Snippet } from 'svelte';
	import type { Figure, RunLevel } from './types';

	let {
		level,
		motionAllowed,
		acts
	}: {
		level: RunLevel;
		motionAllowed: boolean;
		/** What a reader can do on the run, drawn above its text equivalent: a take-over. */
		acts?: Snippet;
	} = $props();

	const byId = $derived(new Map(level.steps.map((s) => [s.id, s])));
	const decided = $derived(level.steps.filter((s) => s.decisions?.length));
	const produced = $derived(level.steps.filter((s) => s.state === 'succeeded' && s.exactness));

	function figures(found: Figure[] | undefined): string {
		return (found ?? []).map((f) => `${f.name} ${f.value}`).join(', ');
	}

	function notes(id: string): string[] {
		const step = byId.get(id);
		const found: string[] = [];
		if (step?.wait) {
			found.push(`waits: ${step.wait.account}${step.wait.role ? ` (${step.wait.role})` : ''}`);
		}
		if (step?.takeover?.standing === 'held') found.push(`taken over: ${step.takeover.id}`);
		if (step?.consumption?.length) found.push(figures(step.consumption));
		return found;
	}
</script>

<section class="run" aria-labelledby="run-title">
	<header>
		<Glyph glyph={chosen(level.run.drawn, motionAllowed)} size={44} />
		<div>
			<p class="eyebrow">Run {level.run.id}</p>
			<h1 id="run-title">{level.summary}</h1>
			<p class="meta">
				Process <a href={processLink(level.run.process_version)}>{level.run.process_version}</a
				>{#if level.run.rehearsal}&#32;· a rehearsal{/if}
			</p>
		</div>
	</header>

	<dl class="consumed">
		<dt>Consumed so far</dt>
		<dd data-figures="run">{figures(level.run.consumed) || 'nothing'}</dd>
	</dl>

	<Graph steps={level.steps} {motionAllowed} {notes} />

	{#if decided.length || produced.length}
		<ul class="more">
			{#each decided as step (step.id)}
				{#each step.decisions ?? [] as d (d.id)}
					<li>
						<Glyph glyph={chosen(d.drawn, motionAllowed)} size={22} />
						{step.id}: <a href={requestsLink(d.id)}>{d.id}</a>, {d.status}
					</li>
				{/each}
			{/each}
			{#each produced as step (step.id)}
				<li><a href={originLink(level.run.id, step.id)}>Where the result of {step.id} came from</a></li>
			{/each}
		</ul>
	{/if}

	{@render acts?.()}

	{#if level.exactness}
		<ExactnessStatement statement={level.exactness} />
	{/if}

	<section class="text" aria-label="The run as text">
		<h2>As text</h2>
		<ol>
			<li data-text="summary">{level.summary}</li>
			<li data-text="run">{level.run.text}</li>
			{#each level.steps as step (step.id)}
				<li data-text={step.id}>{step.text}</li>
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
	header {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}
	.meta {
		margin: 0.15rem 0 0;
		opacity: 0.75;
	}
	.meta a {
		color: inherit;
	}
	.consumed {
		display: flex;
		gap: 0.5rem;
		margin: 1rem 0;
	}
	.consumed dt {
		font-weight: 600;
	}
	.consumed dd {
		margin: 0;
		font-variant-numeric: tabular-nums;
	}
	.more {
		list-style: none;
		padding: 0;
	}
	.more li {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		padding: 0.15rem 0;
	}
</style>
