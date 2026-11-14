<!--
	A read that succeeded and found nothing (ADR-0322 §5): said in one sentence, with the next step
	where there is one. Never drawn for a read that failed: that is ErrorState.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let { title, children }: { title: string; children?: Snippet } = $props();
</script>

<div class="empty" data-state="empty">
	<span class="ring" aria-hidden="true"></span>
	<div>
		<p class="title">{title}</p>
		{#if children}<div class="more">{@render children()}</div>{/if}
	</div>
</div>

<style>
	.empty {
		display: flex;
		gap: var(--sp-200);
		align-items: flex-start;
		padding: var(--sp-250) var(--sp-300);
		border-radius: var(--r-lg);
		border: var(--bw-hairline) dashed var(--border-default);
		background: var(--bg-surface);
		max-inline-size: 46rem;
	}
	.ring {
		flex: none;
		inline-size: var(--sp-300);
		block-size: var(--sp-300);
		border-radius: var(--r-full);
		border: var(--bw-thick) solid var(--text-subtle);
	}
	.title {
		margin: 0;
		font-weight: var(--fw-semibold);
	}
	.more {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.more :global(p) {
		margin: var(--sp-050) 0 0;
	}
</style>
