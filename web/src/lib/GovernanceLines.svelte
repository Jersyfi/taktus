<!--
	The start page's section on what governs the work (DEC-0218, ADR-0122): one line per kind the
	reader may see — decision requests, needs, levels and corrections, findings, tenants — saying
	how many are open or waiting, each leading to its page. A kind the surface refuses the reader
	has no line.
-->
<script lang="ts">
	import type { Line } from './governance';

	let { lines }: { lines: Line[] } = $props();
</script>

<section class="governs" aria-labelledby="governs-title">
	<h2 id="governs-title">What governs the work</h2>
	<ul>
		{#each lines as line (line.kind)}
			<li class:waiting={line.waiting} data-line={line.kind}>
				<a href={line.href}>{line.text}</a>
			</li>
		{/each}
	</ul>
</section>

<style>
	.governs {
		margin-bottom: 2rem;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.35rem;
		max-width: 46rem;
	}
	li a {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.45rem 0.8rem;
		border-radius: 12px;
		text-decoration: none;
	}
	li a:hover {
		background: var(--paper-2);
	}
	/* Something waits: a filled dot; nothing waits: an empty one. Form first, colour never alone. */
	li a::before {
		content: '';
		width: 8px;
		height: 8px;
		border-radius: 50%;
		border: 1.5px solid var(--ink-3);
		flex: none;
	}
	li.waiting a::before {
		background: var(--ink);
		border-color: var(--ink);
	}
</style>
