<!--
	The start page's section of what keeps the operation running (ADR-0121, DEC-0218): its own
	sentence first — what needs a look — then one line per kind, each leading to its page. A kind
	the reader may not read says who reads it, and carries no figure.
-->
<script lang="ts">
	import { operationLines, operationSentence, type OperationSummary } from './operation';

	let { summary }: { summary: OperationSummary } = $props();

	const lines = $derived(operationLines(summary));
	const sentence = $derived(operationSentence(summary));
</script>

<section class="operation-lines" aria-labelledby="operation-lines-title">
	<h2 id="operation-lines-title">What keeps the operation running</h2>
	<p class="sentence" data-text="operation">{sentence}</p>
	<ul>
		{#each lines as line (line.kind)}
			<li class:look={line.red} data-kind={line.kind}>
				<a href={line.href}>
					<span class="mark" aria-hidden="true"></span>
					<span class="label">{line.label}</span>
					<span class="text">{line.text}</span>
				</a>
			</li>
		{/each}
	</ul>
</section>

<style>
	.operation-lines {
		margin: var(--sp-600) 0 var(--sp-400);
	}
	.sentence {
		font-family: var(--font-display);
		font-size: var(--fs-500);
		font-weight: var(--fw-bold);
		line-height: var(--lh-tight);
		margin: 0 0 var(--sp-200);
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 15rem), 1fr));
		gap: var(--sp-150);
	}
	a {
		display: grid;
		grid-template-columns: auto 1fr;
		column-gap: var(--sp-150);
		row-gap: var(--sp-050);
		align-items: baseline;
		height: 100%;
		text-decoration: none;
		padding: var(--sp-200);
		border-radius: var(--r-lg);
		background: var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
	}
	a:hover .label {
		text-decoration: underline;
	}
	.look a {
		background: var(--status-danger-surface);
		border-color: var(--status-danger-border);
	}
	/* A ring is calm; a filled dot needs a look. The hue repeats the form, never replaces it. */
	.mark {
		width: 10px;
		height: 10px;
		border-radius: var(--r-full);
		border: var(--bw-thick) solid var(--text-subtle);
		align-self: center;
	}
	.look .mark {
		border-color: var(--status-danger-accent);
		background: var(--status-danger-accent);
	}
	.label {
		font-weight: var(--fw-semibold);
	}
	.text {
		grid-column: 2;
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.look .text,
	.look .label {
		color: var(--status-danger-text);
	}
</style>
