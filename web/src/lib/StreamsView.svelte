<!--
	The organisation seen as value streams (UC-15.6, ADR-0159 §5). Three tiers: the management
	streams above, the core streams from the customer's need to the customer's outcome in the
	middle, the support streams below. Each card shows the role responsible, a bar of its autonomy
	mix and one of its method mix — reproducible kinds first — its flow efficiency, blocked share
	and the department boundaries it crosses, and opens as role swimlanes. Processes no stream
	names are listed after. No figure names a person.
-->
<script lang="ts">
	import { percent } from './acting';
	import { processLink } from './links';
	import { METHOD_ORDER, segments, streamLink, type StreamCard, type StreamMap } from './views';

	let { view }: { view: StreamMap } = $props();

	const TIERS: { key: 'management' | 'core' | 'support'; title: string }[] = [
		{ key: 'management', title: 'Management' },
		{ key: 'core', title: 'Core: from the customer’s need to their outcome' },
		{ key: 'support', title: 'Support' }
	];

	function figure(share: number | null): string {
		return share === null ? '—' : percent(share);
	}
</script>

{#snippet card(stream: StreamCard)}
	<li class="card {stream.kind}" data-stream={stream.stream}>
		<a href={streamLink(stream.stream)}>
			{#if stream.kind === 'core'}<p class="edge">{stream.trigger}</p>{/if}
			<h3>{stream.name}</h3>
			<p class="muted">Responsible: the role {stream.role}</p>
			<span class="bar" aria-hidden="true">
				{#each segments(stream.figures.autonomy, ['1', '2', '3', '4']) as s (s.key)}
					<span class="part level-{s.key}" style="flex: {s.share}"></span>
				{/each}
			</span>
			<span class="bar" aria-hidden="true">
				{#each segments(stream.figures.methods, METHOD_ORDER) as s (s.key)}
					<span class="part method-{s.key}" style="flex: {s.share}"></span>
				{/each}
			</span>
			<dl>
				<div><dt>Flow efficiency</dt><dd>{figure(stream.figures.flow_efficiency)}</dd></div>
				<div><dt>Blocked</dt><dd>{figure(stream.figures.blocked_share)}</dd></div>
				<div><dt>Boundaries crossed</dt><dd>{stream.figures.crossings.length}</dd></div>
			</dl>
			{#if stream.kind === 'core'}<p class="edge end">{stream.outcome}</p>{/if}
		</a>
		<p class="text">{stream.text}</p>
	</li>
{/snippet}

<section class="streams" aria-labelledby="streams-title">
	<p class="eyebrow">The organisation as value streams · {view.days} days</p>
	<h1 id="streams-title">{view.summary}</h1>
	{#each TIERS as tier (tier.key)}
		{#if view[tier.key].length}
			<h2>{tier.title}</h2>
			<ul class="tier {tier.key}">
				{#each view[tier.key] as stream (stream.stream)}{@render card(stream)}{/each}
			</ul>
		{/if}
	{/each}
	{#if view.outside.length}
		<h2>In no stream</h2>
		<ul class="outside">
			{#each view.outside as p (p.process)}<li><a href={processLink(p.process)}>{p.name}</a></li>{/each}
		</ul>
	{/if}
	<p class="muted">No figure names a person.</p>
</section>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	.tier,
	.outside {
		list-style: none;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
		gap: 0.7rem;
	}
	.card {
		background: var(--paper-2);
		border-radius: 18px;
		padding: 0.8rem 0.9rem;
	}
	.card.core {
		border-left: 4px solid var(--reproducible);
	}
	.card a {
		color: inherit;
		text-decoration: none;
		display: grid;
		gap: 0.35rem;
	}
	h3 {
		font-family: var(--serif);
		margin: 0;
	}
	.edge {
		font-size: 0.8rem;
		color: var(--ink-3);
		margin: 0;
	}
	.edge.end {
		text-align: right;
	}
	.bar {
		display: flex;
		height: 0.5rem;
		border-radius: 4px;
		overflow: hidden;
		background: var(--line);
	}
	.part.level-1 { background: var(--person); }
	.part.level-2 { background: var(--waiting); }
	.part.level-3 { background: var(--variable); }
	.part.level-4 { background: var(--reproducible); }
	.part.method-rule,
	.part.method-statistics,
	.part.method-ml,
	.part.method-neural,
	.part.method-wait { background: var(--reproducible); }
	.part.method-llm,
	.part.method-worker { background: var(--variable); }
	.part.method-human { background: var(--person); }
	dl {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.3rem;
		margin: 0;
	}
	dt {
		font-size: 0.72rem;
		color: var(--ink-3);
	}
	dd {
		margin: 0;
		font-family: var(--serif);
	}
	.text,
	.muted {
		color: var(--ink-2);
		font-size: 0.82rem;
		margin: 0.3rem 0 0;
	}
</style>
