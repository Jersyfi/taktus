<!--
	The Takt of the last 60 minutes (ADR-0323 §3): one mark per minute, as high as the changes
	recorded in it; a minute with a failure carries a mark of the alert family above it — a form,
	not a colour alone. Only the newest arrival moves, once; every earlier mark is still, and
	nothing from the past is replayed as motion. A minute without a change is flat: an idle tenant
	looks idle. Hidden from assistive technology; its sentence says the same.
-->
<script lang="ts">
	import type { Minute } from './takt';

	let {
		drawn,
		arrival = 0,
		arrivedAt = null,
		still = false
	}: {
		drawn: Minute[];
		/** How many changes arrived since the page opened: a new one moves its minute's mark once. */
		arrival?: number;
		/** The minute the newest arrival was recorded in. */
		arrivedAt?: number | null;
		/** Motion is not allowed: nothing moves. */
		still?: boolean;
	} = $props();

	const STEP = 10;
	const HIGH = 40;
	const BASE = 44;
	const most = $derived(Math.max(1, ...drawn.map((m) => m.count)));
	function height(count: number): number {
		if (count === 0) return 2;
		return Math.max(6, Math.round((Math.sqrt(count) / Math.sqrt(most)) * HIGH));
	}
	const busy = $derived(drawn.some((m) => m.count > 0));
</script>

<svg
	class="takt"
	class:idle={!busy}
	viewBox="0 0 {drawn.length * STEP} 48"
	preserveAspectRatio="none"
	aria-hidden="true"
	focusable="false"
	data-motion={!still && arrival > 0 ? 'arrival' : 'none'}
>
	<line class="base" x1="0" x2={drawn.length * STEP} y1={BASE + 1} y2={BASE + 1} />
	{#each drawn as minute, i (minute.start)}
		{@const h = height(minute.count)}
		{@const newest = minute.start === arrivedAt}
		{#if newest && !still && arrival > 0}
			{#key arrival}
				<rect class="tick arrived" x={i * STEP + 2} y={BASE - h} width={STEP - 4} height={h} rx="1.5" data-count={minute.count} />
			{/key}
		{:else}
			<rect class="tick" class:quiet={minute.count === 0} x={i * STEP + 2} y={BASE - h} width={STEP - 4} height={h} rx="1.5" data-count={minute.count} />
		{/if}
		{#if minute.failed}
			<path class="failure" d="M{i * STEP + STEP / 2} {BASE - h - 9} l4 6 l-8 0 z" data-failed={minute.failed} />
		{/if}
	{/each}
</svg>

<style>
	.takt {
		display: block;
		inline-size: 100%;
		block-size: var(--sp-600);
		overflow: visible;
	}
	.base {
		stroke: var(--border-subtle);
		stroke-width: 1;
	}
	.tick {
		fill: var(--accent-primary);
		transform-box: fill-box;
		transform-origin: bottom;
	}
	.tick.quiet {
		fill: var(--border-subtle);
	}
	.failure {
		fill: var(--family-alert);
	}
	/* The one new arrival rises once, at the design system's highlight; nothing repeats. */
	.arrived {
		animation: arrive var(--motion-highlight-duration) var(--motion-highlight-easing) 1;
	}
	@keyframes arrive {
		from {
			transform: scaleY(0.2);
			opacity: 0.4;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.arrived {
			animation: none;
		}
	}
	@media (forced-colors: active) {
		.tick {
			fill: CanvasText;
		}
		.failure {
			fill: Mark;
		}
	}
</style>
