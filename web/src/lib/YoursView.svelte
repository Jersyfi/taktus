<!--
	The reader's own page (ADR-0015, principle 14, UC-9.5): how long runs waited on the reader's
	own decisions — their own share of the waiting on a person — each decision with its time, and
	beside it the reader's role and department, only aggregated and withheld over fewer than two
	deciders. Nobody else reads this page: the surface computes it for its reader alone. No figure
	here is computed by the page; it is shown as handed over, rounded for reading.
-->
<script lang="ts">
	import { duration } from './duration';
	import { runLink } from './links';
	import type { ResponseAggregate, ResponseTimes } from './types';

	let { times }: { times: ResponseTimes } = $props();

	const own = $derived(times.own ?? []);
	const groups = $derived([
		...(times.by_role ?? []).map((a) => ({ kind: 'role', ...a })),
		...(times.by_department ?? []).map((a) => ({ kind: 'department', ...a }))
	]);

	function figure(a: ResponseAggregate): string {
		if (a.withheld || a.median_seconds == null) return `withheld: ${a.withheld ?? 'no figure'}`;
		return `median ${duration(a.median_seconds)} over ${a.decisions} decisions`;
	}
</script>

<section class="yours" aria-labelledby="yours-title">
	<p class="eyebrow">Yours</p>
	<h1 id="yours-title">
		{#if times.own_total_seconds != null}
			Runs waited {duration(times.own_total_seconds)} on your decisions.
		{:else}
			No run has waited on a decision of yours.
		{/if}
	</h1>
	<p class="private" data-private>Only you see this page. Nobody reads these times under your name.</p>

	{#if own.length}
		<section aria-label="Your decisions">
			<h2>Your decisions</h2>
			{#if times.own_median_seconds != null}
				<p class="muted" data-figures="own">Your median time to answer: {duration(times.own_median_seconds)}.</p>
			{/if}
			<ul class="own">
				{#each own as o (o.request_id)}
					<li>
						<span class="id">{o.request_id}</span>
						<a href={runLink(o.run_id)}>{o.run_id}</a>
						<span>{duration(o.seconds)}</span>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if groups.length}
		<section aria-label="Your role and department, aggregated">
			<h2>Beside your role and department</h2>
			<ul class="groups">
				{#each groups as g (`${g.kind}:${g.group}`)}
					<li><strong>{g.group}</strong> <span class="muted">({g.kind})</span> — {figure(g)}</li>
				{/each}
			</ul>
		</section>
	{/if}

	<section class="text" aria-label="This page as text">
		<h2>As text</h2>
		<ol>
			<li>
				{times.own_total_seconds != null
					? `Runs waited ${duration(times.own_total_seconds)} on your decisions.`
					: 'No run has waited on a decision of yours.'}
			</li>
			{#each own as o (o.request_id)}
				<li>{o.request_id} in run {o.run_id}: {duration(o.seconds)}.</li>
			{/each}
			{#each groups as g (`${g.kind}:${g.group}`)}
				<li>{g.kind} {g.group}: {figure(g)}.</li>
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
	.private {
		display: inline-block;
		font-size: 0.85rem;
		padding: 0.3rem 0.8rem;
		border-radius: 999px;
		border: 1px solid var(--line);
		color: var(--ink-2);
	}
	.muted {
		color: var(--ink-2);
	}
	ul {
		list-style: none;
		padding: 0;
		max-width: 40rem;
	}
	.own li,
	.groups li {
		display: flex;
		gap: 1rem;
		padding: 0.45rem 0;
		border-bottom: 1px solid var(--line);
	}
	.own li span:last-child {
		margin-left: auto;
		font-variant-numeric: tabular-nums;
	}
	.id {
		font-family: var(--mono);
		font-size: 0.8rem;
		color: var(--ink-3);
	}
</style>
