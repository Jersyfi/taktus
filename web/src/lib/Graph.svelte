<!--
	Steps as a graph: each at its place by its dependencies, lines from a step to the steps that
	follow it, each drawn from its glyph with motion or without. Below each step's name, the
	short notes its level gives. Hidden from assistive technology: every level writes the same
	out as text.
-->
<script lang="ts">
	import Glyph from './Glyph.svelte';
	import { chosen } from './motion.svelte';
	import { place } from './layout';
	import type { Drawn } from './types';

	interface Node {
		id: string;
		depends_on?: string[];
		drawn: Drawn;
	}

	let {
		steps,
		motionAllowed,
		notes = () => []
	}: { steps: Node[]; motionAllowed: boolean; notes?: (id: string) => string[] } = $props();

	const COLUMN = 200;
	const ROW = 132;
	/** The middle of a step's glyph, from the top of its place, and the room around it. */
	const MIDDLE = 28;
	const GAP = 34;
	const placed = $derived(place(steps));
	const at = $derived(new Map(placed.map((p) => [p.id, p])));
	const width = $derived(Math.max(1, ...placed.map((p) => p.column + 1)) * COLUMN);
	const height = $derived(Math.max(1, ...placed.map((p) => p.row + 1)) * ROW);
	const edges = $derived(
		steps.flatMap((s) =>
			(s.depends_on ?? []).filter((d) => at.has(d)).map((d) => ({ from: at.get(d)!, to: at.get(s.id)! }))
		)
	);
</script>

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
	{#each steps as step (step.id)}
		{@const p = at.get(step.id)!}
		<div class="step" style="left: {p.column * COLUMN}px; top: {p.row * ROW}px" data-step={step.id}>
			<Glyph glyph={chosen(step.drawn, motionAllowed)} />
			<span class="name">{step.id}</span>
			{#each notes(step.id) as note, i (i)}
				<span class="note">{note}</span>
			{/each}
		</div>
	{/each}
</div>

<style>
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
	.note {
		opacity: 0.8;
		font-size: 0.75rem;
	}
</style>
