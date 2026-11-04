<!--
	The exactness statement of a process version (UC-6.9): which checks apply, what they cover,
	what they do not cover, and the residual risk. Shown as it is handed over, part by part and
	sentence by sentence: nothing here edits, shortens or rewrites it, and no model writes it.
	`compact` folds it behind its title, for the overview.
-->
<script lang="ts">
	import type { ExactnessStatement } from './types';

	let { statement, compact = false }: { statement: ExactnessStatement; compact?: boolean } =
		$props();
</script>

{#snippet parts()}
	<div class="parts">
		{#each statement.parts as part (part.title)}
			<div class="part" class:residual={part.title === 'The residual risk'}>
				<h3>{part.title}</h3>
				<ul>
					{#each part.lines as line, index (index)}
						<li>{line}</li>
					{/each}
				</ul>
			</div>
		{/each}
	</div>
{/snippet}

<section
	class="exactness"
	aria-label="Exactness statement"
	data-exactness-statement={statement.process_version}
>
	{#if compact}
		<details>
			<summary>Exactness statement of {statement.process_version}</summary>
			{@render parts()}
		</details>
	{:else}
		<h2>Exactness statement</h2>
		<p class="of">{statement.name} ({statement.process_version})</p>
		{@render parts()}
	{/if}
</section>

<style>
	/* The statement where its reader is (#224): a card of its own, its four parts side by side
	   where there is room, the residual risk set apart — what would slip through all checks. */
	.exactness {
		margin: var(--sp-200) 0 var(--sp-300);
		padding: var(--sp-200) var(--sp-250);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-inline-start: 3px solid var(--family-reproducible);
		border-radius: var(--r-lg);
		background: var(--bg-surface);
		max-width: 64rem;
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	h2 {
		margin: 0 0 var(--sp-025);
	}
	.of {
		margin: 0 0 var(--sp-150);
		color: var(--text-primary);
		font-weight: var(--fw-semibold);
	}
	.parts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
		gap: var(--sp-150);
	}
	.part {
		padding: var(--sp-150);
		border-radius: var(--r-md);
		background: var(--bg-surface-sunken);
	}
	.part.residual {
		background: var(--status-warning-surface);
		color: var(--status-warning-text);
	}
	h3 {
		margin: 0 0 var(--sp-050);
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-primary);
	}
	.residual h3 {
		color: inherit;
	}
	ul {
		margin: 0;
		padding-inline-start: var(--sp-200);
	}
	li + li {
		margin-top: var(--sp-050);
	}
	details > .parts {
		margin-top: var(--sp-150);
	}
	summary {
		cursor: pointer;
		font-weight: var(--fw-medium);
		color: var(--text-primary);
	}
	/* Folded on the overview: no card of its own inside the process's card. */
	details {
		margin: 0;
	}
	.exactness:has(details) {
		padding: var(--sp-100) var(--sp-150);
		background: var(--bg-surface-sunken);
		border-color: transparent;
		border-inline-start-color: var(--family-reproducible);
		margin: var(--sp-150) 0 0;
	}
</style>
