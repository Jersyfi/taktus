<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import { motion } from '../lib/motion.svelte';

	let { children }: { children: Snippet } = $props();

	onMount(() => motion.listen());
</script>

<div class="page">
	<header class="bar">
		<a class="home" href="#/">Taktus</a>
		<label class="calm">
			<input
				type="checkbox"
				checked={motion.stoppedByReader || motion.reducedBySystem}
				disabled={motion.reducedBySystem}
				onchange={(e) => (motion.stoppedByReader = e.currentTarget.checked)}
			/>
			Stop motion{#if motion.reducedBySystem}&#32;(the system asks for it){/if}
		</label>
	</header>
	<main>
		{@render children()}
	</main>
</div>

<style>
	/* Paper and ink. A family's hue is added on top of its form (M1.20, DEC-0185); every
	   distinction is already carried by membrane, nucleus and motion. */
	:global(:root) {
		--paper: oklch(0.972 0.007 85);
		--ink: oklch(0.23 0.012 260);
		--ink-2: oklch(0.46 0.012 260);
		--ink-3: oklch(0.62 0.01 260);
		--line: oklch(0.86 0.01 85);
		--reproducible: oklch(0.5 0.12 240);
		--variable: oklch(0.6 0.16 50);
		--person: oklch(0.52 0.12 150);
		--waiting: oklch(0.55 0.01 260);
		--text: var(--ink);
		--muted: var(--ink-2);
		--surface: var(--paper);
		color-scheme: light dark;
	}
	@media (prefers-color-scheme: dark) {
		:global(:root) {
			--paper: oklch(0.165 0.008 260);
			--ink: oklch(0.94 0.008 85);
			--ink-2: oklch(0.74 0.01 85);
			--ink-3: oklch(0.58 0.01 85);
			--line: oklch(0.29 0.01 260);
			--reproducible: oklch(0.76 0.11 235);
			--variable: oklch(0.8 0.13 65);
			--person: oklch(0.78 0.12 150);
			--waiting: oklch(0.68 0.01 260);
		}
	}
	:global(body) {
		margin: 0;
		background: var(--surface);
		color: var(--text);
		font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
	}
	.page {
		max-width: 72rem;
		margin: 0 auto;
		padding: 0 1rem 3rem;
	}
	.bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--line);
		margin-bottom: 1.25rem;
	}
	.home {
		color: inherit;
		font-weight: 700;
		text-decoration: none;
	}
	.calm {
		font-size: 0.9rem;
		color: var(--muted);
	}
</style>
