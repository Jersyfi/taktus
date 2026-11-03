<!--
	One value stream as role swimlanes (UC-15.6, ADR-0159 §6). A column for each process in the
	order of the stream; a lane for Taktus's reproducible methods, one for its variable methods,
	then one per role a person acts in, in the order the stream first needs it. Each step is a
	chip in its column and lane; a dashed mark in a role's lane shows a step that falls back to that
	role. The toggle overlays the structure: each role lane names the units its holders sit in, and
	each handover that crosses a unit is marked. A role's waiting is shown only where at least two
	hold it. No figure names a person.
-->
<script lang="ts">
	import { hours, percent } from './acting';
	import { processLink } from './links';
	import { fallbacks, grid, type StreamLanes } from './views';

	let { view }: { view: StreamLanes } = $props();
	let departments = $state(false);

	const rows = $derived(grid(view));
	const crossed = $derived(new Set(view.card.figures.crossings.map((c) => `${c.to_process}/${c.to_step}`)));
</script>

<section class="lanes" aria-labelledby="lanes-title">
	<p class="eyebrow"><a href="#/streams">Value streams</a> · {view.card.kind}</p>
	<h1 id="lanes-title">{view.card.name}</h1>
	<p class="muted">From {view.card.trigger} to {view.card.outcome}. Responsible: the role {view.card.role}.</p>
	<p class="muted">{view.summary}</p>
	<label class="toggle"><input type="checkbox" bind:checked={departments} /> Show departments</label>

	<div class="scroll" role="region" aria-label="Swimlanes" tabindex="-1">
		<table>
			<thead>
				<tr>
					<th scope="col">Lane</th>
					{#each view.columns as column (column.process)}
						<th scope="col"><a href={processLink(column.version ?? column.process)}>{column.name}</a>
							{#if column.level}<span class="muted"> · level {column.level}</span>{/if}</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each rows as row (row.lane.key)}
					<tr class="lane {row.lane.kind}" data-lane={row.lane.key}>
						<th scope="row">
							{row.lane.title}
							{#if departments && row.lane.units.length}<span class="units">{row.lane.units.join(', ')}</span>{/if}
							{#if row.lane.kind === 'role'}<span class="muted">{row.lane.waiting_seconds ? `waited on ${hours(row.lane.waiting_seconds)}` : ''}</span>{/if}
						</th>
						{#each row.cells as chips, i (view.columns[i]!.process)}
							<td>
								{#each chips as chip (chip.step)}
									<span
										class="chip method-{chip.method}"
										class:crossing={departments && crossed.has(`${chip.process}/${chip.step}`)}
										title={chip.text}
										data-chip="{chip.process}/{chip.step}">{chip.step}{chip.exactness ? ` · ${chip.exactness[0]!.toUpperCase()}` : ''}</span>
								{/each}
								{#each fallbacks(view, row.lane, view.columns[i]!.process) as chip (chip.step)}
									<span class="chip fallback" title={chip.text} data-fallback="{chip.process}/{chip.step}">{chip.step} ↓</span>
								{/each}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<ul class="texts">
		{#each view.lanes as lane (lane.key)}<li>{lane.text}</li>{/each}
		{#each view.card.figures.crossings as crossing (crossing.text)}<li class="crossing-text">{crossing.text}</li>{/each}
	</ul>
	<p class="muted">
		Flow efficiency {view.card.figures.flow_efficiency === null ? '—' : percent(view.card.figures.flow_efficiency)} ·
		blocked {view.card.figures.blocked_share === null ? '—' : percent(view.card.figures.blocked_share)}.
		No figure names a person.
	</p>
</section>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.84rem;
	}
	.scroll {
		overflow-x: auto;
		max-width: 100%;
	}
	table {
		border-collapse: separate;
		border-spacing: 0.3rem;
		min-width: 100%;
	}
	th,
	td {
		vertical-align: top;
		text-align: left;
		font-size: 0.84rem;
	}
	tbody th {
		min-width: 9rem;
	}
	td {
		background: var(--paper-2);
		border-radius: 10px;
		padding: 0.35rem;
		min-width: 8rem;
	}
	.lane.role td {
		background: color-mix(in oklch, var(--person) 8%, var(--paper-2));
	}
	.units {
		display: block;
		color: var(--ink-3);
		font-size: 0.76rem;
	}
	.chip {
		display: inline-block;
		margin: 0.15rem;
		padding: 0.15rem 0.45rem;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: var(--paper);
	}
	.chip.method-llm,
	.chip.method-worker {
		border-color: var(--variable);
	}
	.chip.method-human {
		border-color: var(--person);
	}
	.chip.fallback {
		border-style: dashed;
		color: var(--ink-2);
	}
	.chip.crossing {
		outline: 2px solid var(--alert);
	}
	.texts {
		color: var(--ink-2);
		font-size: 0.82rem;
	}
</style>
