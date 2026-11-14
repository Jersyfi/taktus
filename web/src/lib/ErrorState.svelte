<!--
	A read that failed (ADR-0322 §5): a 5xx answer, a lost network, a body that is no JSON. Said as
	a failure, with the surface's own words and a way to read again; never shown as empty and never
	as a read that goes on.
-->
<script lang="ts">
	import type { Problem } from './types';

	let { what, problem, onRetry }: { what: string; problem: Problem; onRetry?: () => void } = $props();

	const said = $derived(
		problem.status === 0
			? problem.detail || 'The surface could not be reached.'
			: `The surface answered ${problem.status}${problem.detail ? `: ${problem.detail}` : problem.title ? ` (${problem.title})` : ''}.`
	);
</script>

<div class="error" role="alert" data-state="failed" data-status={problem.status}>
	<span class="mark" aria-hidden="true">!</span>
	<div>
		<p class="title">{what} could not be read.</p>
		<p class="detail">{said}</p>
		{#if onRetry}<button type="button" onclick={onRetry}>Read again</button>{/if}
	</div>
</div>

<style>
	.error {
		display: flex;
		gap: var(--sp-200);
		align-items: flex-start;
		padding: var(--sp-250) var(--sp-300);
		border-radius: var(--r-lg);
		border: var(--bw-hairline) solid var(--status-danger-border);
		border-inline-start-width: var(--bw-thick);
		background: var(--status-danger-surface);
		color: var(--status-danger-text);
		max-inline-size: 46rem;
		margin-block: var(--sp-300);
	}
	.mark {
		flex: none;
		display: grid;
		place-items: center;
		inline-size: var(--sp-300);
		block-size: var(--sp-300);
		border-radius: var(--r-full);
		border: var(--bw-thick) solid currentColor;
		font-weight: var(--fw-bold);
		font-size: var(--fs-100);
	}
	.title {
		margin: 0;
		font-weight: var(--fw-semibold);
	}
	.detail {
		margin: var(--sp-050) 0 var(--sp-150);
		font-size: var(--fs-100);
	}
</style>
