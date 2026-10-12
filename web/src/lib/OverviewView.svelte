<!--
	The overview of UC-6.10 as one body (ADR-0067, amended 2026-10-12; DEC-0185). It opens with a
	sentence that says what works right now. Each area holds its processes; each process is an
	organ drawn as the cells of its active version, joined by vessels. A cell moves only while a
	run of that version runs it. Beside it, how many of its runs work and how many wait — the run
	component's own figures — and the steps running right now, each leading down to its run.
	Written out below as its text equivalent.
-->
<script lang="ts">
	import Glyph from './Glyph.svelte';
	import Graph from './Graph.svelte';
	import { chosen } from './motion.svelte';
	import { processLink, runLink } from './links';
	import type { OverviewLevel } from './types';

	let { level, motionAllowed }: { level: OverviewLevel; motionAllowed: boolean } = $props();
</script>

<section class="overview" aria-labelledby="overview-title">
	<p class="eyebrow">Overview</p>
	<h1 id="overview-title">{level.summary}</h1>
	{#each level.areas as area (area.id)}
		<section class="area" aria-label="Area {area.name}" data-area={area.id}>
			<div class="area-head">
				<h2>{area.name}</h2>
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
									<span class="level" title="Autonomy level {process.autonomy_level}">L{process.autonomy_level}</span>
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
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}

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
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	h1 {
		max-width: 24ch;
		margin-bottom: 2rem;
	}
	.area {
		margin-bottom: 2.5rem;
	}
	.area-head {
		display: flex;
		align-items: baseline;
		gap: 1rem;
		flex-wrap: wrap;
	}
	.figures,
	.meta {
		color: var(--ink-2);
		font-size: 0.85rem;
		margin: 0.15rem 0;
	}
	/* The body: every process an organ of soft tissue; one that works stands out a little. */
	.organs {
		list-style: none;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(19rem, 1fr));
		gap: 0.9rem;
	}
	.organ {
		border-radius: 28px;
		padding: 1.1rem 1.25rem 1rem;
		background:
			radial-gradient(80% 90% at 30% 20%, color-mix(in oklch, var(--reproducible) 4%, transparent), transparent 70%),
			var(--paper-2);
		min-width: 0;
	}
	.organ.busy {
		background:
			radial-gradient(80% 90% at 30% 20%, color-mix(in oklch, var(--reproducible) 7%, transparent), transparent 70%),
			color-mix(in oklch, var(--paper-2) 70%, var(--paper));
		box-shadow: inset 0 0 0 1px var(--line);
	}
	.head {
		display: flex;
		justify-content: space-between;
		gap: 0.6rem;
		align-items: baseline;
		font-weight: 600;
	}
	.head a {
		text-decoration: none;
	}
	.head a:hover {
		text-decoration: underline;
	}
	.level {
		font-family: var(--mono);
		font-size: 0.72rem;
		font-weight: 400;
		color: var(--ink-2);
		border: 1px solid var(--line);
		border-radius: 6px;
		padding: 0 0.35rem;
	}
	.running {
		list-style: none;
		padding: 0;
		margin: 0.5rem 0 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.running li {
		display: flex;
		gap: 0.35rem;
		align-items: center;
		font-size: 0.8rem;
		padding: 0.15rem 0.6rem 0.15rem 0.2rem;
		border-radius: 999px;
		background: var(--paper);
		border: 1px solid var(--line);
	}
</style>
