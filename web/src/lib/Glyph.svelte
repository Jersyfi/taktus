<!--
	One element drawn from its glyph, and nothing else (ADR-0059). A step is a cell (DEC-0185):
	membrane, nucleus, rings, cytoplasm and badge. Every token is carried on the drawing as a data
	attribute of the same name, so that a test can hold what was drawn to what was handed over.
	The text equivalent is the drawing's accessible name and its title.
-->
<script lang="ts">
	import type { Glyph } from './types';
	import { beads, circle, FILLS, fluid, HUES, NUCLEI, PERIODS, R, STATE_MARKS, STILL_MARKS } from './cells';

	let { glyph, size = 56 }: { glyph: Glyph; size?: number } = $props();

	const uid = $props.id();
	const small = $derived(size < 24);
	const hue = $derived(HUES[glyph.membrane] ?? 'var(--ink-2)');
	/** A cell at work carries its family's hue in full; at rest it is quieter. */
	const working = $derived(glyph.motion !== 'none' || glyph.still_mark !== 'none');
	const line = $derived(
		glyph.subject === 'step' && !working ? `color-mix(in oklch, ${hue} 58%, var(--ink-3))` : hue
	);
	const stroke = $derived(small ? 3.2 : 1.8);
	const cytoplasm = $derived(glyph.fill === 'hatched' ? `url(#${uid}-hatch)` : (FILLS[glyph.fill] ?? 0) > 0 ? hue : 'none');
	const density = $derived(glyph.fill === 'hatched' ? 1 : (FILLS[glyph.fill] ?? 0));
	const nucleus = $derived(NUCLEI[glyph.nucleus] ?? []);
	const aura = $derived(STILL_MARKS[glyph.still_mark] ?? null);
	const badge = $derived(STATE_MARKS[glyph.state_mark] ?? '');
	/** The phase of a motion follows the clock, so that a redraw never restarts it and every
	 * reproducible cell beats in phase with every other. */
	const delay = $derived(
		glyph.motion in PERIODS ? -((typeof performance === 'object' ? performance.now() / 1000 : 0) % PERIODS[glyph.motion]!) : 0
	);
	const shapes = [fluid(0), fluid(1), fluid(2)];
</script>

<svg
	class="glyph motion-{glyph.motion}"
	viewBox="0 0 100 100"
	width={size}
	height={size}
	role="img"
	aria-label={glyph.text}
	data-subject={glyph.subject}
	data-membrane={glyph.membrane}
	data-nucleus={glyph.nucleus}
	data-rings={glyph.rings}
	data-fill={glyph.fill}
	data-state-mark={glyph.state_mark}
	data-motion={glyph.motion}
	data-still-mark={glyph.still_mark}
>
	<title>{glyph.text}</title>
	<defs>
		<pattern id="{uid}-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
			<line x1="0" y1="0" x2="0" y2="6" stroke={hue} stroke-width="1.4" stroke-opacity="0.7" />
		</pattern>
		<radialGradient id="{uid}-cloud">
			<stop offset="0" stop-color={line} stop-opacity="0.75" />
			<stop offset="0.55" stop-color={line} stop-opacity="0.28" />
			<stop offset="1" stop-color={line} stop-opacity="0" />
		</radialGradient>
		<radialGradient id="{uid}-halo">
			<stop offset="0.55" stop-color={hue} stop-opacity="0.22" />
			<stop offset="1" stop-color={hue} stop-opacity="0" />
		</radialGradient>
	</defs>
	{#if aura !== null}
		<circle
			class="aura"
			cx="50"
			cy="50"
			r="47"
			fill="none"
			stroke={hue}
			stroke-width={small ? 4 : 1.6}
			stroke-linecap="round"
			stroke-dasharray={aura || undefined}
		/>
	{/if}
	<g class="body" style="animation-delay: {delay}s">
		{#if glyph.motion !== 'none'}
			<circle cx="50" cy="50" r="46" fill="url(#{uid}-halo)" />
		{/if}
		{#if glyph.membrane === 'beaded'}
			<path d={circle(R)} fill={cytoplasm} fill-opacity={density} stroke={line} stroke-width={stroke} />
			{#each beads(small ? 8 : 12) as [x, y], i (i)}
				<circle cx={x} cy={y} r={small ? 5 : 1.9} fill={line} />
			{/each}
		{:else if glyph.membrane === 'fluid'}
			<path d={shapes[0]} fill={cytoplasm} fill-opacity={density} stroke={line} stroke-width={stroke} stroke-linejoin="round">
				{#if glyph.motion === 'shimmer'}
					<animate
						attributeName="d"
						dur="{PERIODS['shimmer']}s"
						begin="{delay}s"
						repeatCount="indefinite"
						calcMode="spline"
						keyTimes="0;0.27;0.64;1"
						keySplines=".45 0 .55 1;.45 0 .55 1;.45 0 .55 1"
						values="{shapes[0]};{shapes[1]};{shapes[2]};{shapes[0]}"
					/>
				{/if}
			</path>
		{:else if glyph.membrane === 'soft'}
			<path d={circle(R)} fill={cytoplasm} fill-opacity={density} stroke={line} stroke-opacity="0.28" stroke-width={small ? 9 : 8} />
			<path d={circle(R)} fill="none" stroke={line} stroke-width={small ? 2.6 : 1.4} />
		{:else if glyph.membrane === 'dormant'}
			<path
				d={circle(R)}
				fill={cytoplasm}
				fill-opacity={density}
				stroke={line}
				stroke-width={stroke}
				stroke-dasharray={small ? '5 6' : '2.5 4.5'}
				stroke-linecap="round"
			/>
		{:else if glyph.membrane === 'tissue'}
			<rect x="12" y="24" width="76" height="52" rx="26" fill={cytoplasm} fill-opacity={density} stroke={line} stroke-width={stroke} />
			{#each [34, 50, 66] as x (x)}
				<circle cx={x} cy="50" r="5" fill="var(--ink-3)" />
			{/each}
		{:else if glyph.membrane === 'crystal'}
			<path d={circle(R)} fill={line} fill-opacity="0.86" />
			<path d={circle(9)} fill="var(--paper)" fill-opacity="0.9" />
		{:else if glyph.membrane === 'root'}
			<path d="M24,30 Q50,88 76,30" fill="none" stroke={line} stroke-width="2" />
			<path d="M50,64 V92" stroke={line} stroke-width="2" />
			<circle cx="50" cy="38" r="6" fill="var(--ink-3)" />
		{:else if glyph.membrane === 'signal'}
			<path d="M50,56 V10" stroke={line} stroke-width="1.8" />
			<circle cx="50" cy="12" r="5" fill={line} />
			<path d={circle(24)} transform="translate(0,14)" fill={cytoplasm === 'none' ? 'none' : line} fill-opacity={density ? density + 0.1 : 0} stroke={line} stroke-width={stroke} />
		{/if}
		{#if glyph.rings === 'inner_membrane'}
			<path d={circle(glyph.subject === 'result' ? R - 8 : R - 6)} fill="none" stroke={glyph.subject === 'result' ? 'var(--paper)' : line} stroke-width={small ? 2.4 : 1.2} />
		{:else if glyph.rings === 'pore'}
			<path d="M50,{50 - R - 1} V{small ? 6 : 8}" stroke={line} stroke-width={small ? 3.2 : 1.6} />
			<circle cx="50" cy={small ? 6 : 8} r={small ? 4 : 2.6} fill={line} />
		{:else if glyph.rings === 'tolerance_band'}
			<path d={circle(R + 7)} fill="none" stroke={line} stroke-width={small ? 2.4 : 1} stroke-dasharray={small ? '3 4' : '1 3.2'} />
		{/if}
		{#each nucleus as part, i (i)}
			{#if 'dot' in part}
				<circle cx={part.dot[0]} cy={part.dot[1]} r={part.dot[2] * (small ? 1.25 : 1)} fill={line} />
			{:else if 'ring' in part}
				<circle cx={part.ring[0]} cy={part.ring[1]} r={part.ring[2]} fill="none" stroke={line} stroke-width={part.ring[3]} />
			{:else if 'line' in part}
				<line x1={part.line[0]} y1={part.line[1]} x2={part.line[2]} y2={part.line[3]} stroke={line} stroke-width={small ? 2 : 1.4} />
			{:else if 'cloud' in part}
				<circle cx="50" cy="50" r={part.cloud} fill="url(#{uid}-cloud)" />
			{/if}
		{/each}
	</g>
	{#if badge}
		{#if small}
			<circle cx="74" cy="74" r="9" fill="var(--ink)" />
		{:else}
			<g transform="translate(74,74) scale(2.1)">
				<circle r="6.4" fill="var(--paper)" stroke="var(--line)" stroke-width="0.7" />
				<path d={badge} fill="none" stroke="var(--ink)" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" />
			</g>
		{/if}
	{/if}
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
	/* Only a running step moves (ADR-0059 §2): a reproducible cell contracts in the shared beat,
	   a variable one drifts while its membrane changes shape, a person's cell breathes. */
	.motion-pulse .body {
		animation: contract 1.2s cubic-bezier(0.3, 0, 0.2, 1) infinite;
	}
	.motion-shimmer .body {
		animation: drift 3.1s ease-in-out infinite;
	}
	.motion-swell .body {
		animation: breathe 4.2s ease-in-out infinite;
	}
	@keyframes contract {
		0%, 100% { transform: scale(1); }
		12% { transform: scale(0.9); }
		30% { transform: scale(1.03); }
		45% { transform: scale(1); }
	}
	@keyframes drift {
		0%, 100% { transform: translate(0, 0) rotate(0deg); }
		27% { transform: translate(1.2px, -0.8px) rotate(4deg); }
		64% { transform: translate(-1px, 0.9px) rotate(-3deg); }
	}
	@keyframes breathe {
		0%, 100% { transform: scale(0.95); }
		50% { transform: scale(1.06); }
	}
	@media (prefers-reduced-motion: reduce) {
		.body {
			animation: none !important;
		}
	}
</style>
