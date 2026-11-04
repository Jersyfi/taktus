<!--
	The overview of UC-6.10 as one body (ADR-0067, amended 2026-10-12; DEC-0185). It opens with a
	sentence that says what works right now. Each area holds its processes; each process is an
	organ drawn as the cells of its active version, joined by vessels. A cell moves only while a
	run of that version runs it. Beside it, how many of its runs work and how many wait — the run
	component's own figures — and the steps running right now, each leading down to its run.
	Written out below as its text equivalent.
-->
<script lang="ts">
	import ExactnessStatement from './ExactnessStatement.svelte';
	import Glyph from './Glyph.svelte';
	import Graph from './Graph.svelte';
	import { chosen } from './motion.svelte';
	import { processLink, runLink } from './links';
	import { areaTitle } from './today';
	import type { Snippet } from 'svelte';
	import type { OverviewLevel } from './types';

	let {
		level,
		motionAllowed,
		lead,
		between,
		after
	}: {
		level: OverviewLevel;
		motionAllowed: boolean;
		/** Under the sentence: the state of the page's stream (ADR-0178 §3). */
		lead?: Snippet;
		/** Before what runs: what waits for the reader. */
		between?: Snippet;
		/** After what runs, before the text equivalent. */
		after?: Snippet;
	} = $props();
</script>

<section class="overview" aria-labelledby="overview-title">
	<header class="hero">
		<p class="eyebrow">Today</p>
		<h1 id="overview-title">{level.summary}</h1>
		{@render lead?.()}
	</header>
	{@render between?.()}
	<h2 class="what-runs">What runs</h2>
	{#each level.areas as area (area.id)}
		{@const headed = areaTitle(area)}
		<section class="area" aria-label="Area {headed.title}" data-area={area.id}>
			<div class="area-head">
				<h2>{headed.title}</h2>
				{#if headed.detail}<p class="area-id" title="The tenant's identifier">{headed.detail}</p>{/if}
				<p class="figures" data-figures="area:{area.id}">
					{area.working} working · {area.waiting} waiting
				</p>
			</div>
			{#if area.processes.length === 0}
				<p>No process you may see.</p>
			{:else}
				<ul class="organs">
					{#each area.processes as process (process.id)}
						<li class="organ" class:busy={process.working > 0 || process.waiting > 0} data-process={process.id}>
							<div class="head">
								<a href={processLink(process.active_version ? `${process.id}@${process.active_version}` : process.id)}
									>{process.name}</a>
								{#if process.autonomy_level !== undefined}
									<span class="level" title="Autonomy level {process.autonomy_level}"
										><span class="steps" aria-hidden="true"
											>{#each [1, 2, 3, 4] as n (n)}<span class:on={n <= (process.autonomy_level ?? 0)}></span>{/each}</span
										>L{process.autonomy_level}</span
									>
								{/if}
							</div>
							{#if process.cells?.length}
								<Graph steps={process.cells} {motionAllowed} compact />
							{/if}
							<p class="figures" data-figures="process:{process.id}">
								{process.working} working · {process.waiting} waiting
							</p>
							{#if process.running?.length}
								<ul class="running">
									{#each process.running as step (`${step.run}/${step.step}`)}
										<li>
											<Glyph glyph={chosen(step.drawn, motionAllowed)} size={22} />
											<a href={runLink(step.run)}>{step.step}</a>
											<span class="meta">{step.run}</span>
										</li>
									{/each}
								</ul>
							{/if}
							{#if process.exactness}
								<ExactnessStatement statement={process.exactness} compact />
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}

	{@render after?.()}

	<section class="text" aria-label="The overview as text">
		<h2>As text</h2>
		<ol>
			<li data-text="summary">{level.summary}</li>
			{#each level.areas as area (area.id)}
				<li data-text="area:{area.id}">{area.text}</li>
				{#each area.processes as process (process.id)}
					<li data-text="process:{process.id}">{process.text}</li>
					{#each process.running ?? [] as step (`${step.run}/${step.step}`)}
						<li data-text="step:{step.run}/{step.step}">{step.text}</li>
					{/each}
				{/each}
			{/each}
		</ol>
	</section>
</section>

<style>
	.area-id {
		margin: 0;
		font-family: var(--font-mono);
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
	.hero {
		position: relative;
		padding: var(--sp-300) 0 var(--sp-400);
		margin-bottom: var(--sp-300);
	}
	/* The beat under the sentence: the signature into the primary hue, the Takt of the page. */
	.hero::after {
		content: '';
		position: absolute;
		inset-inline-start: 0;
		inset-block-end: 0;
		width: min(100%, 22rem);
		height: 4px;
		border-radius: var(--r-full);
		background: linear-gradient(to right, var(--accent-signature), var(--accent-primary) 60%, transparent);
	}
	h1 {
		font-size: clamp(var(--fs-600), 5.4vw, var(--fs-800));
		max-width: 22ch;
		margin-bottom: var(--sp-200);
	}
	.what-runs {
		margin-top: var(--sp-600);
	}
	.area {
		margin-bottom: var(--sp-500);
	}
	.area-head {
		display: flex;
		align-items: baseline;
		gap: var(--sp-200);
		flex-wrap: wrap;
	}
	.area-head h2 {
		margin: 0;
		font-family: var(--font-display);
		font-size: var(--fs-500);
		font-weight: var(--fw-bold);
		letter-spacing: -0.01em;
		text-transform: none;
		color: var(--text-primary);
	}
	.figures,
	.meta {
		color: var(--text-secondary);
		font-size: var(--fs-075);
		margin: var(--sp-025) 0;
		font-family: var(--font-mono);
	}
	/* The body: every process an organ, raised on the canvas; one that works carries a ring. */
	.organs {
		list-style: none;
		padding: 0;
		margin: var(--sp-200) 0 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));
		align-items: start;
		gap: var(--sp-200);
	}
	.organ {
		position: relative;
		border-radius: var(--r-xl);
		padding: var(--sp-200) var(--sp-250);
		background: var(--bg-surface);
		box-shadow: var(--shadow-raised);
		border: var(--bw-hairline) solid var(--border-subtle);
		min-width: 0;
		overflow: hidden;
	}
	.organ.busy {
		border-color: var(--family-reproducible);
		background:
			radial-gradient(120% 80% at 0% 0%, var(--family-reproducible-surface), transparent 60%),
			var(--bg-surface);
	}
	.head {
		display: flex;
		justify-content: space-between;
		gap: var(--sp-100);
		align-items: baseline;
		font-weight: var(--fw-semibold);
		font-size: var(--fs-300);
		line-height: var(--lh-snug);
	}
	.head a {
		text-decoration: none;
	}
	.head a:hover {
		text-decoration: underline;
	}
	.level {
		display: inline-flex;
		align-items: center;
		gap: var(--sp-050);
		font-family: var(--font-mono);
		font-size: var(--fs-075);
		font-weight: var(--fw-regular);
		color: var(--text-secondary);
		flex: none;
	}
	/* The level as four steps, filled up to it; the figure beside it says the same. */
	.steps {
		display: inline-flex;
		align-items: flex-end;
		gap: 2px;
		height: 12px;
	}
	.steps span {
		width: 3px;
		border-radius: var(--r-xs);
		background: var(--border-subtle);
	}
	.steps span:nth-child(1) {
		height: 40%;
	}
	.steps span:nth-child(2) {
		height: 60%;
	}
	.steps span:nth-child(3) {
		height: 80%;
	}
	.steps span:nth-child(4) {
		height: 100%;
	}
	.steps span.on {
		background: var(--accent-primary);
	}
	.running {
		list-style: none;
		padding: 0;
		margin: var(--sp-100) 0 0;
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-050);
	}
	.running li {
		display: flex;
		gap: var(--sp-050);
		align-items: center;
		font-size: var(--fs-075);
		padding: var(--sp-025) var(--sp-150) var(--sp-025) var(--sp-025);
		border-radius: var(--r-full);
		background: var(--bg-canvas);
		border: var(--bw-hairline) solid var(--border-subtle);
	}
</style>
