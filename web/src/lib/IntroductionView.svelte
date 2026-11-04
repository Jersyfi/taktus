<!--
	A tenant's introduction in stages (ADR-0137, ADR-0191, UC-9.6), for the plan's responsible
	role: each stage with its processes, their levels, runs, missed runs and incidents, whether
	it holds, and the open action where the rule allows it. Taktus never opens a stage by itself.
-->
<script lang="ts">
	import OperationPage from './OperationPage.svelte';
	import {
		figuresLine,
		introductionLines,
		mayOpen,
		processLine,
		stateLabel,
		type Introduction,
		type StageDocument
	} from './introduction';

	let {
		intro,
		onOpen,
		problem = null,
		opening = null
	}: {
		intro: Introduction;
		onOpen: (stage: StageDocument) => void;
		problem?: string | null;
		opening?: string | null;
	} = $props();

	let asked: string | null = $state(null);
	const lines = $derived(introductionLines(intro));
</script>

<OperationPage eyebrow="Introduction" sentence={intro.summary} {lines}>
	{#if problem}<p class="mark look" role="alert">{problem}</p>{/if}
	{#if intro.stages.length === 0}
		<p class="empty">No stages are declared for this tenant.</p>
	{:else}
		<ol class="records stages">
			{#each intro.stages as stage (stage.stage.id)}
				{@const open = stage.state !== 'closed'}
				<li class="record" data-stage={stage.stage.id} data-state={stage.state}>
					<p class="mark" class:look={stage.state === 'not_holding'}>
						Stage {stage.position} · {stateLabel(stage.state)}{#if stage.proposed}{' '}· proposed for opening{/if}
					</p>
					<h3>{stage.stage.name}</h3>
					<p class="meta">Holds when: {stage.condition.join('; ')}.</p>
					{#if stage.figures}
						<p class="meta" data-figures={stage.stage.id}>{figuresLine(stage.figures)}</p>
					{/if}
					<ul class="processes">
						{#each stage.processes as p (p.process)}
							<li>{processLine(p, open)}</li>
						{/each}
					</ul>
					{#if stage.missing.length}
						<p class="meta">{open ? 'Not holding yet' : 'Its opening lacks'}: {stage.missing.join('; ')}.</p>
					{/if}
					{#if mayOpen(stage)}
						{#if asked === stage.stage.id}
							<p class="meta">
								Opening stage {stage.position} lifts the ceiling of its processes to the levels it grants. You open it; Taktus
								records that you did.
							</p>
							<div class="acts">
								<button type="button" disabled={opening === stage.stage.id} onclick={() => onOpen(stage)}>Open the stage</button>
								<button type="button" class="quiet" onclick={() => (asked = null)}>Not now</button>
							</div>
						{:else}
							<button type="button" onclick={() => (asked = stage.stage.id)}>Open stage {stage.position}…</button>
						{/if}
					{/if}
				</li>
			{/each}
		</ol>
	{/if}
</OperationPage>

<style>
	.processes {
		margin: var(--sp-100) 0;
		padding-left: var(--sp-250);
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.acts {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-100);
	}
</style>
