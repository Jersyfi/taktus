<!--
	A read under way (ADR-0322 §5): the page's shape in quiet planes, and the words of what is read
	for a screen reader. It does not shimmer: a reading page is not work being done.
-->
<script lang="ts">
	let { label, lines = 3 }: { label: string; lines?: number } = $props();
</script>

<div class="skeleton" role="status" aria-busy="true" data-state="loading">
	<span class="sr-only">{label}</span>
	<span class="block head" aria-hidden="true"></span>
	{#each Array.from({ length: lines }, (_, i) => i) as i (i)}
		<span class="block" aria-hidden="true" style:inline-size="{92 - i * 14}%"></span>
	{/each}
</div>

<style>
	.skeleton {
		display: grid;
		gap: var(--sp-150);
		max-inline-size: var(--layout-content-max);
		padding-block: var(--sp-200);
	}
	.block {
		display: block;
		block-size: var(--sp-200);
		border-radius: var(--r-sm);
		background: var(--bg-recess);
	}
	.head {
		block-size: var(--sp-500);
		inline-size: 60%;
		border-radius: var(--r-md);
		margin-block-end: var(--sp-100);
	}
</style>
