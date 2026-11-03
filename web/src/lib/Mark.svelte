<!--
	The mark of Taktus: a beaded membrane — the reproducible cell (ADR-0059) — around the signature
	plane and its core, in the design system's brand parts (ADR-0177). It beats once for each change
	the page's stream delivers, and never where motion is not allowed.
-->
<script lang="ts">
	let { size = 28, beat = 0, still = false }: { size?: number; beat?: number; still?: boolean } = $props();
	const BEADS = Array.from({ length: 12 }, (_, i) => {
		const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
		return [16 + 12 * Math.cos(a), 16 + 12 * Math.sin(a)] as const;
	});
</script>

<svg class="mark" viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" focusable="false">
	{#key beat}
		<g class="ring" class:beats={!still && beat > 0}>
			<circle cx="16" cy="16" r="12" class="membrane" />
			{#each BEADS as [x, y], i (i)}
				<circle cx={x} cy={y} r="1.55" class="bead" />
			{/each}
		</g>
	{/key}
	<circle cx="16" cy="16" r="6.6" class="plane" />
	<circle cx="16" cy="16" r="2.4" class="core" />
</svg>

<style>
	.mark {
		flex: none;
		overflow: visible;
	}
	.membrane {
		fill: none;
		stroke: var(--brand-outline);
		stroke-width: 1.4;
	}
	.bead {
		fill: var(--brand-outline);
	}
	.plane {
		fill: var(--brand-plane);
	}
	.core {
		fill: var(--brand-core);
	}
	.ring {
		transform-origin: 16px 16px;
	}
	.beats {
		animation: beat var(--motion-emphasis-duration) var(--motion-emphasis-easing);
	}
	@keyframes beat {
		40% {
			transform: scale(1.14);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.beats {
			animation: none;
		}
	}
</style>
