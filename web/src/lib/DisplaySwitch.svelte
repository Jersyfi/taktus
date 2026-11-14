<!--
	Picture or text, for this page (ADR-0322 §2): two buttons, the pressed one is the mode shown.
	The default for every page is set in the account group.
-->
<script lang="ts">
	import { display, type Display } from './display.svelte';

	let { page }: { page: string } = $props();
	const shown = $derived(display.of(page));
	const MODES: { id: Display; label: string }[] = [
		{ id: 'picture', label: 'Picture' },
		{ id: 'text', label: 'Text' }
	];
</script>

<div class="switch" role="group" aria-label="Show as">
	{#each MODES as m (m.id)}
		<button type="button" aria-pressed={shown === m.id} onclick={() => display.choose(page, m.id)}>{m.label}</button>
	{/each}
</div>

<style>
	.switch {
		display: inline-flex;
		padding: var(--sp-025);
		gap: var(--sp-025);
		background: var(--bg-recess);
		border-radius: var(--r-full);
	}
	button {
		min-height: var(--density-control-sm-min);
		padding: 0 var(--sp-150);
		border: none;
		border-radius: var(--r-full);
		background: transparent;
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-secondary);
	}
	button[aria-pressed='true'] {
		background: var(--bg-surface);
		color: var(--text-brand);
		box-shadow: var(--shadow-raised);
	}
</style>
