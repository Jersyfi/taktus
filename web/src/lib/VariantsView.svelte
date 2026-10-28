<!--
	How a process really runs (UC-9.7, ADR-0147 §4). Four figures first: the share on the designed
	path, the runs, the runs in flight, the variants. Then the designed path as a row of steps, and
	each variant as a bar of its share with its deviations marked at their steps; the waiting at
	each step split by cause; the waiting per role, shown only where at least two hold the role;
	and the proposals, each decided by a person in a change in dialogue. There is no filter by
	person.
-->
<script lang="ts">
	import { deviations, hours, percent, type VariantsView } from './acting';
	import { changeLink, processLink, runLink } from './links';

	let { view }: { view: VariantsView } = $props();

	const WORDS: Record<string, string> = {
		fell_back: 'to a person',
		retried: 'retried',
		anchored: 'anchor',
		taken_over: 'taken over'
	};
</script>

<section class="variants" aria-labelledby="variants-title">
	<p class="eyebrow">How <a href={processLink(view.process_id)}>{view.process_id}</a> really runs</p>
	<h1 id="variants-title">{view.summary}</h1>

	<dl class="tiles">
		<div><dt>On the designed path</dt><dd>{view.on_designed_path === null ? '—' : percent(view.on_designed_path)}</dd></div>
		<div><dt>Runs ended</dt><dd>{view.runs}</dd></div>
		<div><dt>In flight</dt><dd>{view.in_flight}</dd></div>
		<div><dt>Variants</dt><dd>{view.variants.length}</dd></div>
	</dl>

	<ol class="designed" aria-label="The designed path">
		{#each view.designed as step (step)}<li><code>{step}</code></li>{/each}
	</ol>

	<ul class="paths">
		{#each view.variants as variant (variant.text)}
			<li class:designed={variant.designed} data-variant={variant.path.join('|') || 'designed'}>
				<span class="bar" style="width: {Math.max(2, variant.share * 100)}%"></span>
				<p>{variant.text}</p>
				<p class="marks">
					{#each deviations(variant) as d, i (i)}<span class="mark {d.what}">{WORDS[d.what] ?? d.what} · {d.step}</span>{/each}
					{#if variant.end !== 'finished'}<span class="mark ended">{variant.end}</span>{/if}
				</p>
				<p class="muted">
					e.g. {#each variant.examples as run, i (run)}{#if i > 0}, {/if}<a href={runLink(run)}>{run}</a>{/each}
				</p>
			</li>
		{/each}
	</ul>

	{#if view.waiting.length}
		<h2>Waiting, by step and cause</h2>
		<ul class="waiting">
			{#each view.waiting as w (w.step_id)}
				<li data-waiting={w.step_id}>
					<code>{w.step_id}</code> · {hours(w.seconds)}{w.share === null ? '' : ` · ${percent(w.share)} of the waiting`}
					<span class="split" aria-hidden="true">
						{#each Object.entries(w.by_cause) as [cause, seconds] (cause)}
							<span class="part {cause.split('.')[0]}" style="flex: {seconds}"></span>
						{/each}
					</span>
					<span class="muted">{Object.entries(w.by_cause).map(([c, s]) => `${c} ${hours(s)}`).join(' · ')}</span>
				</li>
			{/each}
		</ul>
	{/if}

	{#if view.roles.length}
		<h2>Waiting on roles</h2>
		<ul class="roles">
			{#each view.roles as r (r.role)}<li data-role={r.role}>{r.text}</li>{/each}
		</ul>
	{/if}

	{#if view.proposals.length}
		<h2>Proposals</h2>
		<ul class="proposals">
			{#each view.proposals as p (`${p.kind}:${p.step_id}`)}
				<li data-proposal="{p.kind}:{p.step_id}">
					<p>{p.text}</p>
					<p class="muted">{p.evidence}. <a href={changeLink(view.process_id)}>Decide it in a change in dialogue</a></p>
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
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
		gap: 0.6rem;
	}
	.tiles div {
		background: var(--paper-2);
		border-radius: 18px;
		padding: 0.7rem 0.9rem;
	}
	.tiles dt {
		color: var(--ink-3);
		font-size: 0.75rem;
	}
	.tiles dd {
		margin: 0;
		font-family: var(--serif);
		font-size: 1.6rem;
	}
	.designed {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		list-style: none;
		padding: 0;
		margin: 1.2rem 0 0.6rem;
	}
	.designed li {
		border: 1.5px solid var(--reproducible);
		border-radius: 999px;
		padding: 0.1rem 0.7rem;
	}
	.designed li + li::before {
		content: '→ ';
		color: var(--ink-3);
	}
	.paths,
	.waiting,
	.roles,
	.proposals {
		list-style: none;
		padding: 0;
	}
	.paths li {
		position: relative;
		padding: 0.5rem 0.8rem;
		margin: 0.4rem 0;
		border-radius: 14px;
		background: var(--paper-2);
		overflow: hidden;
	}
	.paths li.designed {
		box-shadow: inset 0 0 0 1.5px var(--reproducible);
	}
	.bar {
		position: absolute;
		inset: 0 auto 0 0;
		background: color-mix(in oklch, var(--reproducible) 12%, transparent);
	}
	.paths p {
		position: relative;
		margin: 0.15rem 0;
	}
	.mark {
		font-size: 0.75rem;
		border-radius: 999px;
		padding: 0 0.5rem;
		margin-right: 0.3rem;
		border: 1px solid var(--line);
	}
	.mark.fell_back {
		border-color: var(--person);
	}
	.mark.retried {
		border-style: dashed;
	}
	.mark.ended {
		border-color: var(--alert);
		color: var(--alert);
	}
	.waiting li {
		margin: 0.5rem 0;
	}
	.split {
		display: flex;
		height: 6px;
		border-radius: 3px;
		overflow: hidden;
		margin: 0.25rem 0;
		max-width: 28rem;
	}
	.part {
		background: var(--waiting);
	}
	.part.wait {
		background: var(--person);
	}
	.part.limit {
		background: var(--variable);
	}
	.proposals li {
		border-left: 3px solid var(--ink);
		padding-left: 0.7rem;
		margin: 0.6rem 0;
	}
	a {
		color: inherit;
	}
</style>
