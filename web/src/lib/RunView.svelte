<!--
	The run level of UC-6.10: where one run stands. Drawn from the level the surface hands over
	and from nothing else: every glyph is the vocabulary's, picked with motion or without by the
	reader's setting, and every figure is the run component's. The same states and figures are
	written out below the drawing, as its text equivalent. It leads to its process (ADR-0064).
-->
<script lang="ts">
	import DisplaySwitch from './DisplaySwitch.svelte';
	import ExactnessStatement from './ExactnessStatement.svelte';
	import TextEquivalent from './TextEquivalent.svelte';
	import { display, type Display } from './display.svelte';
	import Glyph from './Glyph.svelte';
	import Graph from './Graph.svelte';
	import { chosen } from './motion.svelte';
	import { originLink, processLink, requestsLink, stagesLink } from './links';
	import { spendLink } from './spend';
	import type { Snippet } from 'svelte';
	import type { Figure, RunLevel } from './types';

	let {
		level,
		motionAllowed,
		mode,
		acts
	}: {
		level: RunLevel;
		motionAllowed: boolean;
		/** Picture or text (ADR-0322); the reader's choice for the run page where not given. */
		mode?: Display;
		/** What a reader can do on the run, drawn above its text equivalent: a take-over. */
		acts?: Snippet;
	} = $props();

	const shown = $derived(mode ?? display.of('run'));
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
				· <a href={spendLink(level.run.id)}>where it spent</a>
				· <a href={stagesLink(level.run.id)}>its stages</a>
			</p>
		</div>
	</header>

	<!-- In the text mode the run's own text says what it consumed: said once (ADR-0322 §3). -->
	{#if shown === 'picture'}
		<dl class="consumed">
			<dt>Consumed so far</dt>
			<dd data-figures="run">{figures(level.run.consumed) || 'nothing'}</dd>
		</dl>
	{/if}

	<div class="tools"><DisplaySwitch page="run" /></div>
	{#if shown === 'picture'}
		<Graph steps={level.steps} {motionAllowed} {notes} />
	{/if}
	<TextEquivalent label="The run as text" mode={shown}>
		<li data-text="summary">{level.summary}</li>
		<li data-text="run">{level.run.text}</li>
		{#each level.steps as step (step.id)}
			<li data-text={step.id}>{step.text}</li>
		{/each}
	</TextEquivalent>

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
</section>

<style>
	.tools {
		display: flex;
		justify-content: flex-end;
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
