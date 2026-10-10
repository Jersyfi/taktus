<!--
	The run level of UC-6.10: where one run stands. Drawn from the level the surface hands over
	and from nothing else: every glyph is the vocabulary's, picked with motion or without by the
	reader's setting, and every figure is the run component's. The same states and figures are
	written out below the drawing, as its text equivalent.
-->
<script lang="ts">
	import Glyph from './Glyph.svelte';
	import { chosen } from './motion.svelte';
	import { place } from './layout';
	import type { Figure, RunLevel } from './types';

	let { level, motionAllowed }: { level: RunLevel; motionAllowed: boolean } = $props();

	const COLUMN = 200;
	const ROW = 132;
	/** The middle of a step's glyph, from the top of its place, and the room around it. */
	const MIDDLE = 28;
	const GAP = 34;
	const placed = $derived(place(level.steps));
	const at = $derived(new Map(placed.map((p) => [p.id, p])));
	const width = $derived(Math.max(1, ...placed.map((p) => p.column + 1)) * COLUMN);
	const height = $derived(Math.max(1, ...placed.map((p) => p.row + 1)) * ROW);
	const edges = $derived(
		level.steps.flatMap((s) =>
			(s.depends_on ?? [])
				.filter((d) => at.has(d))
				.map((d) => ({ from: at.get(d)!, to: at.get(s.id)! }))
		)
	);

	function figures(found: Figure[] | undefined): string {
		return (found ?? []).map((f) => `${f.name} ${f.value}`).join(', ');
	}
</script>

<section class="run" aria-labelledby="run-title">
	<header>
		<Glyph glyph={chosen(level.run.drawn, motionAllowed)} size={44} />
		<div>
			<h1 id="run-title">Run {level.run.id}</h1>
			<p class="meta">
				Process {level.run.process_version}{#if level.run.rehearsal}&#32;· a rehearsal{/if}
			</p>
		</div>
	</header>

	<dl class="consumed">
		<dt>Consumed so far</dt>
		<dd data-figures="run">{figures(level.run.consumed) || 'nothing'}</dd>
	</dl>

	<div class="flow" style="width: {width}px; height: {height}px" aria-hidden="true">
		<svg class="edges" {width} {height}>
			{#each edges as edge (`${edge.from.id}>${edge.to.id}`)}
				<line
					x1={edge.from.column * COLUMN + COLUMN / 2 + GAP}
					y1={edge.from.row * ROW + MIDDLE}
					x2={edge.to.column * COLUMN + COLUMN / 2 - GAP}
					y2={edge.to.row * ROW + MIDDLE}
				/>
			{/each}
		</svg>
		{#each level.steps as step (step.id)}
			{@const p = at.get(step.id)!}
			<div class="step" style="left: {p.column * COLUMN}px; top: {p.row * ROW}px" data-step={step.id}>
				<Glyph glyph={chosen(step.drawn, motionAllowed)} />
				<span class="name">{step.id}</span>
				{#if step.wait}
					<span class="wait">waits: {step.wait.account}{#if step.wait.role}&#32;({step.wait.role}){/if}</span>
				{/if}
				{#if step.consumption?.length}
					<span class="used">{figures(step.consumption)}</span>
				{/if}
			</div>
		{/each}
	</div>

	<section class="text" aria-label="The run as text">
		<h2>As text</h2>
		<ol>
			<li data-text="run">{level.run.text}</li>
			{#each level.steps as step (step.id)}
				<li data-text={step.id}>{step.text}</li>
			{/each}
		</ol>
	</section>
</section>

<style>
	header {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}
	h1 {
		font-size: 1.25rem;
		margin: 0;
	}
	.meta {
		margin: 0.15rem 0 0;
		opacity: 0.75;
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
	.flow {
		position: relative;
		max-width: 100%;
		overflow-x: auto;
	}
	.edges {
		position: absolute;
		inset: 0;
	}
	.edges line {
		stroke: currentColor;
		stroke-opacity: 0.35;
		stroke-width: 1.5;
	}
	.step {
		position: absolute;
		width: 200px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.15rem;
		text-align: center;
		font-size: 0.85rem;
	}
	.name {
		font-weight: 600;
	}
	.wait,
	.used {
		opacity: 0.8;
		font-size: 0.75rem;
	}
	.text ol {
		padding-left: 1.25rem;
		line-height: 1.5;
	}
</style>
