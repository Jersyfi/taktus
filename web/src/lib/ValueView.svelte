<!--
	The value ledger (UC-9.1 to UC-9.3, UC-6.7, ADR-0244): what to do — the proposals, computed on
	every read and changing nothing —, how far the organisation could run without Taktus, a role
	or a supplier — the bus-factor figures, their trend per day and the dependencies as edges —
	and the transformation: each unit's figures and the backlog of potential, every entry of which
	is an expectation, not a result. Each part the surface refused says so on its own. Nothing here
	computes a figure, and no figure names a person.
-->
<script lang="ts">
	import FigureList from './FigureList.svelte';
	import {
		backlogLine,
		edgeLine,
		figureLine,
		proposalKind,
		type Proposals,
		type Transformation,
		type ValueIndex
	} from './figures';

	let {
		proposals,
		index,
		transformation,
		problems = {}
	}: {
		proposals: Proposals | null;
		index: ValueIndex | null;
		transformation: Transformation | null;
		/** What the surface said where it served a part not. */
		problems?: { proposals?: string; index?: string; transformation?: string };
	} = $props();

	const sentence = $derived(
		proposals === null
			? 'The value ledger.'
			: proposals.proposals.length === 0
				? 'No proposal for your roles.'
				: `${proposals.proposals.length} ${proposals.proposals.length === 1 ? 'proposal' : 'proposals'} for your roles.`
	);
</script>

<section aria-labelledby="value-title">
	<p class="eyebrow">Value</p>
	<h1 id="value-title">{sentence}</h1>

	<section aria-labelledby="proposals-title">
		<h2 id="proposals-title">What to do</h2>
		{#if proposals}
			<p class="muted">Computed on every read and stored nowhere. Nothing changes until a person acts.</p>
			<ul class="proposals">
				{#each proposals.proposals as p, i (i)}
					<li data-kind={p.kind}>
						<span class="kind">{proposalKind(p.kind)}</span>
						<span>{p.text}</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="muted" role="alert">{problems.proposals ?? 'Not read.'}</p>
		{/if}
	</section>

	<section aria-labelledby="index-title">
		<h2 id="index-title">Without Taktus, a role or a supplier</h2>
		{#if index}
			<FigureList figures={index.figures} />
			<h3>Per day</h3>
			{#if index.trend.length}
				<div class="scroll">
					<table>
						<thead>
							<tr><th scope="col">Day</th><th scope="col">Processes that cannot run without Taktus</th><th scope="col">Suppliers whose removal breaks a process</th></tr>
						</thead>
						<tbody>
							{#each index.trend as d (d.day)}
								<tr><td>{d.day}</td><td class="n">{d.without_taktus}</td><td class="n">{d.suppliers_broke}</td></tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else}
				<p class="muted">No day in the period.</p>
			{/if}
			<h3>Dependencies</h3>
			{#if index.graph.length}
				<ul class="edges">
					{#each index.graph as e (`${e.kind}:${e.process}:${e.on}`)}
						<li data-edge={e.kind}><code>{e.process}</code> → <code>{e.on}</code> <span class="muted">{edgeLine(e)}</span></li>
					{/each}
				</ul>
			{:else}
				<p class="muted">No dependency is recorded.</p>
			{/if}
		{:else}
			<p class="muted" role="alert">{problems.index ?? 'Not read.'}</p>
		{/if}
	</section>

	<section aria-labelledby="transformation-title">
		<h2 id="transformation-title">The transformation</h2>
		{#if transformation}
			<FigureList figures={transformation.figures} empty="No unit is named for a process." />
			<h3>Backlog of potential</h3>
			{#if transformation.backlog.length}
				<ul class="backlog">
					{#each transformation.backlog as b (`${b.kind}:${b.id}`)}
						<li>
							{#if b.expectation}<span class="expectation" data-expectation>expectation</span>{/if}
							{backlogLine(b)}
						</li>
					{/each}
				</ul>
			{:else}
				<p class="muted">The backlog is empty.</p>
			{/if}
		{:else}
			<p class="muted" role="alert">{problems.transformation ?? 'Not read.'}</p>
		{/if}
	</section>

	<section class="text" aria-label="This page as text">
		<h2>As text</h2>
		<ol>
			<li>{sentence}</li>
			{#each proposals?.proposals ?? [] as p, i (i)}<li>{proposalKind(p.kind)}: {p.text}</li>{/each}
			{#each index?.figures ?? [] as f (`${f.id}:${f.scope}:${f.subject}`)}<li>{figureLine(f)}</li>{/each}
			{#each index?.graph ?? [] as e (`${e.kind}:${e.process}:${e.on}`)}<li>{edgeLine(e)}</li>{/each}
			{#each transformation?.figures ?? [] as f (`${f.id}:${f.scope}:${f.subject}`)}<li>{figureLine(f)}</li>{/each}
			{#each transformation?.backlog ?? [] as b (`${b.kind}:${b.id}`)}<li>Expectation: {backlogLine(b)}</li>{/each}
		</ol>
	</section>
</section>

<style>
	ul {
		list-style: none;
		padding: 0;
		max-width: 48rem;
	}
	li {
		padding: var(--sp-100) 0;
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
	}
	.proposals li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-050) var(--sp-200);
	}
	.kind {
		font-weight: var(--fw-semibold);
		min-width: 10rem;
	}
	.expectation {
		display: inline-block;
		margin-inline-end: var(--sp-100);
		padding: 0 var(--sp-100);
		border-radius: var(--r-sm);
		border: var(--bw-hairline) solid var(--status-info-border);
		background: var(--status-info-surface);
		color: var(--status-info-text);
		font-size: var(--fs-075);
	}
	.scroll {
		max-width: 100%;
		overflow-x: auto;
	}
	.n {
		font-variant-numeric: tabular-nums;
		text-align: end;
	}
	.muted {
		color: var(--text-secondary);
	}
</style>
