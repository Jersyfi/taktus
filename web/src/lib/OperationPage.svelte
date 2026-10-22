<!--
	The frame of every page of what keeps the operation running (ADR-0121): the eyebrow, the
	sentence that says what is happening, the records, and the same again as text (UC-6.10).
	Paper and ink, as every level (DEC-0185); a record that needs a look carries a mark of its own
	form and says so in words, and the alert hue is added on top, never alone.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		eyebrow,
		sentence,
		lines,
		children
	}: { eyebrow: string; sentence: string; lines: string[]; children: Snippet } = $props();
</script>

<section class="operation" aria-labelledby="operation-title">
	<p class="eyebrow">{eyebrow}</p>
	<h1 id="operation-title">{sentence}</h1>
	{@render children()}
	<section class="text" aria-label="This page as text">
		<h2>As text</h2>
		<ol>
			<li data-text="sentence">{sentence}</li>
			{#each lines as line, i (i)}
				<li>{line}</li>
			{/each}
		</ol>
	</section>
</section>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	h1 {
		max-width: 28ch;
		margin-bottom: 2rem;
	}
	/* Every record is a soft card on paper, as the overview's organs are. */
	.operation :global(.records) {
		list-style: none;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(20rem, 1fr));
		gap: 0.9rem;
	}
	.operation :global(.record) {
		border-radius: 24px;
		padding: 1.1rem 1.25rem 1rem;
		background: var(--paper-2);
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.operation :global(.record.look) {
		box-shadow: inset 0 0 0 1.5px color-mix(in oklch, var(--alert) 55%, var(--line));
	}
	.operation :global(.record.done) {
		background: color-mix(in oklch, var(--paper-2) 45%, var(--paper));
		color: var(--ink-2);
	}
	.operation :global(.record h3) {
		font-size: 1rem;
		font-weight: 600;
		margin: 0 0 0.35rem;
	}
	.operation :global(.mark) {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.75rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--ink-2);
		margin: 0 0 0.4rem;
	}
	/* The mark's form carries the distinction: a ring is calm, a filled dot needs a look, a
	   dashed ring was not measured. The hue only repeats it. */
	.operation :global(.mark::before) {
		content: '';
		width: 8px;
		height: 8px;
		border-radius: 50%;
		border: 1.5px solid currentColor;
		flex: none;
	}
	.operation :global(.mark.look) {
		color: var(--alert);
	}
	.operation :global(.mark.look::before) {
		background: currentColor;
	}
	.operation :global(.mark.half::before) {
		background: linear-gradient(90deg, currentColor 50%, transparent 50%);
	}
	.operation :global(.mark.unknown::before) {
		border-style: dashed;
	}
	.operation :global(.facts) {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.2rem 0.9rem;
		font-size: 0.85rem;
		margin: 0.5rem 0 0;
	}
	.operation :global(.facts dt) {
		color: var(--ink-2);
	}
	.operation :global(.facts dd) {
		margin: 0;
	}
	.operation :global(.meta) {
		color: var(--ink-2);
		font-size: 0.85rem;
		margin: 0.15rem 0;
	}
	.operation :global(.id) {
		font-family: var(--mono);
		font-size: 0.78rem;
		color: var(--ink-3);
	}
	.operation :global(details) {
		margin-top: 0.6rem;
		font-size: 0.85rem;
	}
	.operation :global(details ul) {
		padding-left: 1.1rem;
	}
	.operation :global(.empty) {
		color: var(--ink-2);
	}
	@media (max-width: 760px) {
		.operation :global(.records) {
			grid-template-columns: 1fr;
		}
	}
</style>
