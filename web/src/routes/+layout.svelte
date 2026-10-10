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
	:global(:root) {
		--text: #1d1d1f;
		--muted: #5c5c66;
		--surface: #ffffff;
		--line: #d6d6dc;
		color-scheme: light dark;
	}
	@media (prefers-color-scheme: dark) {
		:global(:root) {
			--text: #ececf0;
			--muted: #a4a4b0;
			--surface: #16161a;
			--line: #34343c;
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
