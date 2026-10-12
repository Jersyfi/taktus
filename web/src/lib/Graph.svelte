<!--
	Steps as one tissue: each a cell at its place by its dependencies, vessels from a step to the
	steps that follow it. Into a running step a vessel carries that step's own motion, the work
	arriving; nothing else on it moves (ADR-0059 §2). On a narrow screen the graph runs from top
	to bottom. Below each step's name, the short notes its level gives. Hidden from assistive
	technology: every level writes the same out as text.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import Glyph from './Glyph.svelte';
	import { R } from './cells';
	import { chosen } from './motion.svelte';
	import { place } from './layout';
	import type { Drawn } from './types';

	interface Node {
		id: string;
		/** What the node is called on the page; its id where it has no other name. */
		name?: string;
		depends_on?: string[];
		drawn: Drawn;
	}

	let {
		steps,
		motionAllowed,
		notes = () => [],
		compact = false
	}: {
		steps: Node[];
		motionAllowed: boolean;
		notes?: (id: string) => string[];
		/** Small cells without names: a process drawn among others on the overview. */
		compact?: boolean;
	} = $props();

	/** Whether the screen is narrow; read once mounted, wide until then. */
	let narrow = $state(false);
	onMount(() => {
		if (typeof matchMedia !== 'function') return;
		const query = matchMedia('(max-width: 760px)');
		narrow = query.matches;
		const changed = () => (narrow = query.matches);
		query.addEventListener('change', changed);
		return () => query.removeEventListener('change', changed);
	});

	const vertical = $derived(narrow && !compact);
	const CELL = $derived(compact ? 22 : narrow ? 48 : 56);
	const ACROSS = $derived(compact ? 32 : narrow ? 112 : 150);
	const ALONG = $derived(compact ? 30 : narrow ? 136 : 124);
	const WIDTH = $derived(compact ? 32 : narrow ? 108 : 140);
	/** Where a vessel meets a membrane, from a cell's centre. */
	const REACH = $derived((CELL * R) / 100 + 3);

	const placed = $derived(place(steps));
	const at = $derived(new Map(placed.map((p) => [p.id, p])));
	const columns = $derived(Math.max(1, ...placed.map((p) => p.column + 1)));
	const rows = $derived(Math.max(1, ...placed.map((p) => p.row + 1)));
	const width = $derived((vertical ? rows : columns) * ACROSS);
	const height = $derived((vertical ? columns : rows) * ALONG);
	const glyphs = $derived(new Map(steps.map((s) => [s.id, chosen(s.drawn, motionAllowed)])));

	function corner(id: string): [number, number] {
		const p = at.get(id)!;
		return vertical ? [p.row * ACROSS, p.column * ALONG] : [p.column * ACROSS, p.row * ALONG];
	}
	function centre(id: string): [number, number] {
		const [x, y] = corner(id);
		return [x + WIDTH / 2, y + 4 + CELL / 2];
	}

	const vessels = $derived(
		steps.flatMap((s) =>
			(s.depends_on ?? [])
				.filter((d) => at.has(d))
				.map((d) => {
					const [x1, y1] = centre(d);
					const [x2, y2] = centre(s.id);
					const path = vertical
						? `M${x1},${y1 + REACH + 44} C${x1},${(y1 + y2) / 2 + 22} ${x2},${(y1 + y2) / 2 + 22} ${x2},${y2 - REACH}`
						: `M${x1 + REACH},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2 - REACH},${y2}`;
					return { key: `${d}>${s.id}`, path, motion: glyphs.get(s.id)?.motion ?? 'none' };
				})
		)
	);
</script>

<div class="tissue" class:compact aria-hidden="true">
	<div class="flow" style="width: {width}px; height: {height}px">
		<svg class="vessels" {width} {height}>
			{#each vessels as v (v.key)}
				<path class="wall" d={v.path} />
				<path class="core flow-{v.motion}" d={v.path} />
			{/each}
		</svg>
		{#each steps as step (step.id)}
			{@const [x, y] = corner(step.id)}
			<div class="step" style="left: {x}px; top: {y}px; width: {WIDTH}px" data-step={step.id}>
				<Glyph glyph={glyphs.get(step.id)!} size={CELL} />
				{#if !compact}
					<span class="name">{step.name ?? step.id}</span>
					{#each notes(step.id) as note, i (i)}
						<span class="note">{note}</span>
					{/each}
				{/if}
			</div>
		{/each}
	</div>
</div>

<style>
	.tissue {
		border-radius: 18px;
		background:
			radial-gradient(60% 80% at 20% 30%, color-mix(in oklch, var(--reproducible) 5%, transparent), transparent 70%),
			radial-gradient(50% 70% at 85% 70%, color-mix(in oklch, var(--variable) 4%, transparent), transparent 70%),
			var(--paper-2);
		padding: 1.5rem;
		overflow: auto;
		overscroll-behavior: contain;
		margin: 1rem 0;
	}
	.tissue.compact {
		background: none;
		padding: 0.25rem 0;
		margin: 0.5rem 0;
		border-radius: 0;
	}
	.compact .wall {
		stroke-width: 4;
	}
	.flow {
		position: relative;
	}
	.vessels {
		position: absolute;
		inset: 0;
		overflow: visible;
	}
	.wall {
		fill: none;
		stroke: var(--ink-3);
		stroke-opacity: 0.1;
		stroke-width: 7;
		stroke-linecap: round;
	}
	.core {
		fill: none;
		stroke: var(--ink-3);
		stroke-opacity: 0.5;
		stroke-width: 1.2;
	}
	/* Into a running step a vessel carries that step's motion, and only then. */
	.core.flow-pulse {
		stroke: var(--reproducible);
		stroke-opacity: 0.95;
		stroke-dasharray: 2 10;
		animation: flow-pulse 1.2s linear infinite;
	}
	.core.flow-shimmer {
		stroke: var(--variable);
		stroke-opacity: 0.95;
		stroke-dasharray: 3 7 1 11;
		animation: flow-shimmer 3.1s cubic-bezier(0.6, 0.1, 0.3, 0.9) infinite;
	}
	.core.flow-swell {
		stroke: var(--person);
		stroke-opacity: 0.95;
		stroke-dasharray: 6 14;
		animation: flow-swell 4.2s ease-in-out infinite;
	}
	@keyframes flow-pulse {
		to { stroke-dashoffset: -12; }
	}
	@keyframes flow-shimmer {
		to { stroke-dashoffset: -44; }
	}
	@keyframes flow-swell {
		to { stroke-dashoffset: -20; }
	}
	@media (prefers-reduced-motion: reduce) {
		.core {
			animation: none !important;
		}
	}
	.step {
		position: absolute;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.15rem;
		text-align: center;
		font-size: 0.8rem;
		line-height: 1.25;
	}
	.name {
		font-weight: 600;
	}
	.note {
		color: var(--ink-2);
		font-size: 0.72rem;
	}
</style>
