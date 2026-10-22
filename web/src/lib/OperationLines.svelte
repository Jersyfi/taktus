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
		margin: 2.5rem 0;
	}
	.sentence {
		font-family: var(--serif);
		font-size: 1.35rem;
		line-height: 1.25;
		margin: 0 0 0.9rem;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr));
		gap: 0.6rem;
	}
	a {
		display: grid;
		grid-template-columns: auto auto 1fr;
		align-items: baseline;
		gap: 0.6rem;
		text-decoration: none;
		padding: 0.75rem 1rem;
		border-radius: 18px;
		background: var(--paper-2);
	}
	a:hover .label {
		text-decoration: underline;
	}
	.look a {
		box-shadow: inset 0 0 0 1.5px color-mix(in oklch, var(--alert) 55%, var(--line));
	}
	/* A ring is calm; a filled dot needs a look. The hue repeats the form, never replaces it. */
	.mark {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		border: 1.5px solid var(--ink-3);
		align-self: center;
	}
	.look .mark {
		border-color: var(--alert);
		background: var(--alert);
	}
	.label {
		font-weight: 600;
	}
	.text {
		color: var(--ink-2);
		font-size: 0.88rem;
	}
	@media (max-width: 760px) {
		ul {
			grid-template-columns: 1fr;
		}
	}
</style>
