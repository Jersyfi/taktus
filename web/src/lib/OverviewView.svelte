<!--
	The overview of UC-6.10: the areas a reader may look into, the processes in each, and how busy
	each one is right now — how many of its runs work and how many wait, the run component's own
	figures, counted over the runs the reader may see. The only thing that moves is a step running
	right now. Each process leads down to its process level, each running step to its run.
	Written out below as its text equivalent (ADR-0067).
-->
<script lang="ts">
	import Glyph from './Glyph.svelte';
	import { chosen } from './motion.svelte';
	import { processLink, runLink } from './links';
	import type { OverviewLevel } from './types';

	let { level, motionAllowed }: { level: OverviewLevel; motionAllowed: boolean } = $props();
</script>

<section class="overview" aria-labelledby="overview-title">
	<h1 id="overview-title">Overview</h1>
	{#each level.areas as area (area.id)}
		<section class="area" aria-label="Area {area.name}" data-area={area.id}>
			<h2>{area.name}</h2>
			<p class="figures" data-figures="area:{area.id}">
				{area.working} working · {area.waiting} waiting
			</p>
			{#if area.processes.length === 0}
				<p>No process you may see.</p>
			{:else}
				<ul class="processes">
					{#each area.processes as process (process.id)}
						<li class="process" data-process={process.id}>
							<div class="head">
								<a href={processLink(process.active_version ? `${process.id}@${process.active_version}` : process.id)}
									>{process.name}</a>
								{#if process.autonomy_level !== undefined}
									<span class="meta">level {process.autonomy_level}</span>
								{/if}
							</div>
							<p class="figures" data-figures="process:{process.id}">
								{process.working} working · {process.waiting} waiting
							</p>
							{#if process.running?.length}
								<ul class="running">
									{#each process.running as step (`${step.run}/${step.step}`)}
										<li>
											<Glyph glyph={chosen(step.drawn, motionAllowed)} size={30} />
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
	a {
		color: inherit;
	}
	.figures,
	.meta {
		color: var(--muted);
		font-variant-numeric: tabular-nums;
		margin: 0.15rem 0;
	}
	.processes {
		list-style: none;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 0.75rem;
	}
	.process {
		background: var(--paper-2);
		border-radius: 14px;
		padding: 1rem 1.1rem;
	}
	.head {
		display: flex;
		gap: 0.6rem;
		align-items: baseline;
		font-weight: 600;
	}
	.running {
		list-style: none;
		padding: 0;
		margin: 0.4rem 0 0;
	}
	.running li {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}
</style>
