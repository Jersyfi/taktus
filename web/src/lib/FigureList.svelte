<!--
	Figures as their owners handed them in (ADR-0241): each with its value and unit, or the
	surface's reason it is withheld, marked where it rests on an assumption or is a simulation,
	with its definition and how it was computed one step away. Nothing here computes a figure.
-->
<script lang="ts">
	import { figureMarks, figureValue, type Figure } from './figures';

	let { figures, empty = 'No figure here for your roles.' }: { figures: Figure[]; empty?: string } = $props();
</script>

{#if figures.length === 0}
	<p class="muted">{empty}</p>
{:else}
	<ul class="figures">
		{#each figures as f (`${f.id}:${f.scope}:${f.subject}`)}
			<li data-figure={f.id}>
				<div class="head">
					<span class="subject">{f.subject} <span class="muted">({f.scope})</span></span>
					<span class="value" class:withheld={f.value === null || f.value === undefined}>{figureValue(f)}</span>
				</div>
				<p class="definition">
					<code>{f.id}</code> — {f.definition}
					{#each figureMarks(f) as mark (mark)}<span class="mark" data-mark={mark}>{mark}</span>{/each}
				</p>
				<details>
					<summary>How it was computed</summary>
					<p>{f.method}. Defined and computed by {f.component}.</p>
				</details>
			</li>
		{/each}
	</ul>
{/if}

<style>
	.figures {
		list-style: none;
		padding: 0;
		max-width: 48rem;
	}
	.figures li {
		padding: var(--sp-150) 0;
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-100) var(--sp-300);
		justify-content: space-between;
	}
	.value {
		font-variant-numeric: tabular-nums;
		font-weight: var(--fw-semibold);
	}
	.value.withheld {
		font-weight: var(--fw-medium);
		color: var(--text-secondary);
	}
	.definition {
		margin: var(--sp-050) 0;
		color: var(--text-secondary);
		font-size: var(--fs-075);
	}
	.mark {
		display: inline-block;
		margin-inline-start: var(--sp-100);
		padding: 0 var(--sp-100);
		border-radius: var(--r-sm);
		border: var(--bw-hairline) solid var(--status-info-border);
		background: var(--status-info-surface);
		color: var(--status-info-text);
	}
	.muted {
		color: var(--text-secondary);
	}
	details {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
</style>
