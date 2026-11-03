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
	{#each statement.parts as part (part.title)}
		<h3>{part.title}</h3>
		<ul>
			{#each part.lines as line, index (index)}
				<li>{line}</li>
			{/each}
		</ul>
	{/each}
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
	.exactness {
		margin: 1rem 0 1.5rem;
		padding: 0.9rem 1.1rem;
		border: 1px solid var(--line);
		border-radius: 14px;
		max-width: 56rem;
		color: var(--ink-2);
	}
	h2 {
		margin: 0 0 0.2rem;
		font-size: 1rem;
	}
	h3 {
		margin: 0.8rem 0 0.2rem;
		font-size: 0.9rem;
	}
	.of {
		margin: 0;
		color: var(--muted);
	}
	ul {
		margin: 0.2rem 0;
		padding-left: 1.2rem;
	}
	summary {
		cursor: pointer;
	}
</style>
