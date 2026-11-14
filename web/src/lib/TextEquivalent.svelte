<!--
	A drawing's text equivalent (UC-6.10 §2, ADR-0322 §1). In the picture mode it stays in the
	accessibility tree, hidden from sight, so that a screen reader reads it as before; in the text
	mode it is shown where the drawing was. The drawing itself is hidden from assistive technology.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { Display } from './display.svelte';

	let { label, mode, children }: { label: string; mode: Display; children: Snippet } = $props();
</script>

<section class="text" class:sr-only={mode === 'picture'} aria-label={label} data-display={mode}>
	{#if mode === 'text'}<h2>As text</h2>{/if}
	<ol>
		{@render children()}
	</ol>
</section>
