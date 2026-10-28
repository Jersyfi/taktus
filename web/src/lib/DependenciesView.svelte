<!--
	What depends on what (UC-6.16, ADR-0147 §3), in one of three modes the surface answered:
	*if it goes* — what breaks and what only degrades without one adapter; *where a wrong result
	went* — the step runs it reached, forward, with what left the system; *where data goes* —
	every adapter against the tenant's residency rule. It starts from one selected node and never
	draws the whole tenant. It acts on nothing.
-->
<script lang="ts">
	import type { ActorUse, RemoveView, ResidencyView, WrongResultView } from './acting';
	import { processLink, removeLink, runLink, wrongResultLink } from './links';

	let {
		remove,
		wrong,
		residency
	}: { remove?: RemoveView; wrong?: WrongResultView; residency?: ResidencyView } = $props();
</script>

{#snippet uses(title: string, kind: string, found: ActorUse[])}
	{#if found.length}
		<h2>{title}</h2>
		<ul class="edges {kind}">
			{#each found as u (`${u.process_id}:${u.step_id}`)}
				<li data-use="{u.process_id}:{u.step_id}">
					<a href={processLink(`${u.process_id}@${u.version}`)}>{u.process_id}</a>
					<span class="arrow" aria-hidden="true">→</span>
					<code>{u.step_id}</code>
					<span class="muted">L{u.level}{u.exactness ? ` · ${u.exactness}` : ''}</span>
					<p class="muted">{u.reason}</p>
				</li>
			{/each}
		</ul>
	{/if}
{/snippet}

<section class="dependencies" aria-labelledby="dependencies-title">
	<p class="eyebrow">
		{remove ? 'If it goes' : wrong ? 'Where a wrong result went' : 'Where data goes'}
	</p>
	{#if remove}
		<h1 id="dependencies-title">{remove.summary}</h1>
		{#if remove.removal}
			<p class="muted">
				Evidence: the removal test of {remove.removal.tested_at.slice(0, 10)} found <strong>{remove.removal.verdict}</strong>.
			</p>
		{/if}
		{@render uses('Breaks', 'breaks', remove.breaks)}
		{@render uses('Only degrades', 'degrades', remove.degrades)}
	{:else if wrong}
		<h1 id="dependencies-title">{wrong.summary}</h1>
		<ol class="flow">
			<li class="origin">
				<a href={runLink(wrong.run_id)}>{wrong.run_id}</a> · <code>{wrong.step_id}</code>
				{#if wrong.exactness}<span class="muted">{wrong.exactness}</span>{/if}
				{#each wrong.left_itself as kind (kind)}<span class="egress" title="Left the system">{kind}</span>{/each}
			</li>
			{#each wrong.reached as r (`${r.run_id}:${r.step_id}`)}
				<li data-reached="{r.run_id}:{r.step_id}">
					<a href={runLink(r.run_id)}>{r.run_id}</a> · <code>{r.step_id}</code>
					<span class="muted">{r.process_version}{r.exactness ? ` · ${r.exactness}` : ''}</span>
					{#each r.left as kind (kind)}<span class="egress" title="Left the system">{kind}</span>{/each}
					<a class="muted" href={wrongResultLink(r.run_id, r.step_id)}>follow on</a>
				</li>
			{/each}
		</ol>
		<dl class="counts">
			<div><dt>Affected</dt><dd>{wrong.affected}</dd></div>
			<div><dt>Built on it</dt><dd>{Object.keys(wrong.built_on).length} process versions</dd></div>
			<div><dt>Left the system</dt><dd>{wrong.left}</dd></div>
		</dl>
		<p class="muted">{wrong.since_when}</p>
	{:else if residency}
		<h1 id="dependencies-title">{residency.summary}</h1>
		<ul class="places">
			{#each residency.rows as r (r.adapter)}
				<li class={r.residency} data-residency={r.adapter}>
					<a href={removeLink(r.adapter)}>{r.adapter}</a>
					<span>{r.location ?? 'undeclared'}</span>
					<span class="muted">{r.residency === 'outside' ? 'outside the rule' : r.residency}</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	h1 {
		max-width: 34ch;
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.86rem;
		margin: 0.2rem 0;
	}
	.edges,
	.flow,
	.places {
		list-style: none;
		padding: 0;
	}
	.edges li,
	.flow li,
	.places li {
		padding: 0.55rem 0.8rem;
		margin: 0.4rem 0;
		border-radius: 14px;
		background: var(--paper-2);
	}
	/* What breaks carries a solid edge, what degrades a dashed one: not colour alone. */
	.edges.breaks li {
		border-left: 4px solid var(--alert);
	}
	.edges.degrades li {
		border-left: 4px dashed var(--variable);
	}
	.flow li {
		position: relative;
		margin-left: 1.2rem;
	}
	.flow li::before {
		content: '';
		position: absolute;
		left: -0.9rem;
		top: -0.5rem;
		bottom: 50%;
		border-left: 1.5px solid var(--line);
		border-bottom: 1.5px solid var(--line);
		width: 0.7rem;
	}
	.flow li.origin {
		margin-left: 0;
		box-shadow: inset 0 0 0 1.5px var(--ink);
	}
	.flow li.origin::before {
		display: none;
	}
	.egress {
		margin-left: 0.4rem;
		font-size: 0.72rem;
		border-radius: 999px;
		padding: 0 0.5rem;
		border: 1.5px solid var(--alert);
		color: var(--alert);
	}
	.counts {
		display: flex;
		gap: 1.5rem;
		flex-wrap: wrap;
	}
	.counts dt {
		color: var(--ink-3);
		font-size: 0.75rem;
	}
	.counts dd {
		margin: 0;
		font-size: 1.4rem;
		font-family: var(--serif);
	}
	.places li {
		display: flex;
		gap: 0.8rem;
		flex-wrap: wrap;
	}
	.places li.outside {
		box-shadow: inset 0 0 0 1.5px var(--alert);
	}
	a {
		color: inherit;
	}
</style>
