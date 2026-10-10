<!--
	One element drawn from its glyph, and nothing else (ADR-0059). Every token is carried on the
	drawing as a data attribute of the same name, so that a test can hold what was drawn to what
	was handed over. The text equivalent is the drawing's accessible name and its title.
-->
<script lang="ts">
	import type { Glyph } from './types';
	import { EDGES, OUTLINES, STATE_MARKS, STILL_MARKS } from './shapes';

	let { glyph, size = 56 }: { glyph: Glyph; size?: number } = $props();

	const uid = $props.id();
	const outline = $derived(OUTLINES[glyph.outline] ?? OUTLINES['square']!);
	const edge = $derived(EDGES[glyph.edge ?? 'none'] ?? EDGES['none']!);
	const markPath = $derived(STATE_MARKS[glyph.state_mark] ?? '');
	const ring = $derived(STILL_MARKS[glyph.still_mark] ?? null);
	const fill = $derived(
		glyph.fill === 'full'
			? 'currentColor'
			: glyph.fill === 'hatched'
				? `url(#${uid}-hatch)`
				: 'none'
	);
</script>

<svg
	class="glyph motion-{glyph.motion}"
	viewBox="0 0 100 100"
	width={size}
	height={size}
	role="img"
	aria-label={glyph.text}
	data-subject={glyph.subject}
	data-outline={glyph.outline}
	data-edge={glyph.edge}
	data-exactness-mark={glyph.exactness_mark}
	data-fill={glyph.fill}
	data-state-mark={glyph.state_mark}
	data-motion={glyph.motion}
	data-still-mark={glyph.still_mark}
>
	<title>{glyph.text}</title>
	<defs>
		<pattern id="{uid}-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
			<line x1="0" y1="0" x2="0" y2="8" stroke="currentColor" stroke-width="2" />
		</pattern>
		<clipPath id="{uid}-lower">
			<rect x="0" y="50" width="100" height="50" />
		</clipPath>
		<filter id="{uid}-waver" x="-10%" y="-10%" width="120%" height="120%">
			<feTurbulence type="fractalNoise" baseFrequency="0.06" numOctaves="1" seed="3" />
			<feDisplacementMap in="SourceGraphic" scale="5" />
		</filter>
	</defs>
	<g class="body">
		{#if ring !== null}
			<circle
				class="still"
				cx="50"
				cy="50"
				r="47"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-dasharray={ring || undefined}
				stroke-linecap="round"
			/>
		{/if}
		{#if glyph.fill === 'partial'}
			<path d={outline(38)} fill="currentColor" fill-opacity="0.35" clip-path="url(#{uid}-lower)" />
		{/if}
		<path
			d={outline(38)}
			fill={fill}
			fill-opacity={glyph.fill === 'full' ? 0.35 : 1}
			stroke="currentColor"
			stroke-width={edge.width}
			stroke-linejoin={edge.join}
			stroke-dasharray={edge.dash}
			filter={edge.waver ? `url(#${uid}-waver)` : undefined}
		/>
		{#if glyph.exactness_mark === 'double_outline'}
			<path d={outline(30)} fill="none" stroke="currentColor" stroke-width="2" />
		{:else if glyph.exactness_mark === 'source_notch'}
			<path d="M50,8 V22" stroke="currentColor" stroke-width="4" stroke-linecap="round" />
		{:else if glyph.exactness_mark === 'tilde'}
			<path d="M36,80 Q43,73 50,80 T64,80" fill="none" stroke="currentColor" stroke-width="3" />
		{/if}
		{#if markPath}
			<path d={markPath} fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
		{/if}
	</g>
</svg>

<style>
	.glyph {
		display: inline-block;
		overflow: visible;
		flex: none;
	}
	.body {
		transform-origin: 50px 50px;
		transform-box: view-box;
	}
	/* Only a running step moves (ADR-0059 §2): reproducible steps pulse at a fixed period,
	   variable ones shimmer irregularly, a person's step swells slowly. */
	.motion-pulse .body {
		animation: pulse 1.2s ease-in-out infinite;
	}
	.motion-shimmer .body {
		animation: shimmer 2.3s linear infinite;
	}
	.motion-swell .body {
		animation: swell 4s ease-in-out infinite;
	}
	@keyframes pulse {
		0%, 100% { transform: scale(1); }
		50% { transform: scale(1.08); }
	}
	@keyframes shimmer {
		0% { transform: translate(0, 0) rotate(0deg); opacity: 1; }
		13% { transform: translate(1px, -1px) rotate(1.5deg); opacity: 0.8; }
		29% { transform: translate(-1px, 0) rotate(-1deg); opacity: 1; }
		41% { transform: translate(0, 1px) rotate(2deg); opacity: 0.7; }
		67% { transform: translate(1px, 1px) rotate(-2deg); opacity: 0.95; }
		83% { transform: translate(-1px, -1px) rotate(0.5deg); opacity: 0.75; }
		100% { transform: translate(0, 0) rotate(0deg); opacity: 1; }
	}
	@keyframes swell {
		0%, 100% { transform: scale(0.96); }
		50% { transform: scale(1.06); }
	}
	@media (prefers-reduced-motion: reduce) {
		.body {
			animation: none !important;
		}
	}
</style>
