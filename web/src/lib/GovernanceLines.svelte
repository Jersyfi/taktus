<!--
	The start page's section on what governs the work (DEC-0218, ADR-0122): one line per kind the
	reader may see — decision requests, needs, levels and corrections, findings, tenants — saying
	how many are open or waiting, each leading to its page. A kind the surface refuses the reader
	has no line. The start page draws the lines that wait under *For you*, and the rest under their
	own title (ADR-0178 §3).
-->
<script lang="ts">
	import type { Line } from './governance';

	let { lines, title = 'What governs the work' }: { lines: Line[]; title?: string } = $props();
	const uid = $props.id();

	/** A line's own words, its kind first: "Needs: 1 is open." as "Needs:" and "1 is open." */
	function split(text: string): [string, string] {
		const at = text.indexOf(': ');
		return at < 0 ? ['', text] : [text.slice(0, at + 1), text.slice(at + 2)];
	}
</script>

<section class="governs" aria-labelledby="{uid}-title">
	<h2 id="{uid}-title">{title}</h2>
	<ul>
		{#each lines as line (line.kind)}
			{@const [kind, rest] = split(line.text)}
			<li class:waiting={line.waiting} data-line={line.kind}>
				<a href={line.href}>
					<span class="mark" aria-hidden="true"></span>
					<span class="kind">{kind}</span>
					<span class="rest">{rest}</span>
				</a>
			</li>
		{/each}
	</ul>
</section>

<style>
	.governs {
		margin-bottom: var(--sp-400);
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 17rem), 1fr));
		gap: var(--sp-150);
	}
	a {
		display: grid;
		grid-template-columns: auto 1fr;
		column-gap: var(--sp-150);
		row-gap: var(--sp-025);
		align-items: baseline;
		height: 100%;
		padding: var(--sp-200);
		border-radius: var(--r-lg);
		background: var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		text-decoration: none;
		transition: transform var(--motion-state-duration) var(--motion-state-easing);
	}
	a:hover {
		transform: translateY(-2px);
	}
	.kind {
		font-weight: var(--fw-semibold);
	}
	.rest {
		grid-column: 2;
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	/* Something waits: a filled dot and a raised tile; nothing waits: an empty ring. Form first,
	   colour never alone. */
	.mark {
		width: 10px;
		height: 10px;
		border-radius: var(--r-full);
		border: var(--bw-thick) solid var(--text-subtle);
		align-self: center;
	}
	.waiting a {
		background: var(--accent-primary-subtle);
		border-color: var(--accent-primary);
		box-shadow: var(--shadow-raised);
	}
	.waiting .mark {
		background: var(--accent-primary);
		border-color: var(--accent-primary);
		box-shadow: 0 0 0 4px var(--bg-surface);
	}
	.waiting .rest {
		color: var(--text-primary);
	}
</style>
