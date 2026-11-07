<!--
	What Taktus took off the reader (UC-13.5, ADR-0245 §1): the surface's sentence, each process
	that relieves one of the reader's roles — its runs finished, the minutes a case takes by hand,
	the hours regained and its takeover instructions — and the goals the reader set, each reached
	or not. Below, the reader's own settings: the roles they share it with, their goals, and how
	often a line reaches them. Success is time and the reader's own goals: no points, levels,
	streaks, ranks or comparisons (principle 14). Nothing here computes a figure.
-->
<script lang="ts">
	import { surfaceHref } from './figures';
	import { goalLine, LINES, regained, reliefLine, settingsOf, type Line, type OwnRelief, type ReliefSettings } from './relief';

	let {
		relief,
		problem = null,
		said = null,
		busy = false,
		onSave
	}: {
		relief: OwnRelief;
		problem?: string | null;
		said?: string | null;
		busy?: boolean;
		onSave: (settings: ReliefSettings) => void;
	} = $props();

	let roles = $state('');
	let goals = $state<{ title: string; hours: string | number | null }[]>([]);
	let line = $state<Line>('never');
	let invalid = $state<string | null>(null);

	// The form starts from what the surface holds.
	$effect(() => {
		roles = relief.shared_with.join(', ');
		goals = relief.goals.length
			? relief.goals.map((g) => ({ title: g.title, hours: String(g.hours_per_week) }))
			: [{ title: '', hours: '' }];
	});

	function save(event: SubmitEvent) {
		event.preventDefault();
		const read = settingsOf(roles, goals, line);
		if (!read.ok) {
			invalid = read.problem;
			return;
		}
		invalid = null;
		onSave(read.settings);
	}
</script>

<section class="relief" aria-labelledby="relief-title">
	<h2 id="relief-title">{relief.sentence}</h2>
	<p class="private" data-private>Only you see this unless you share it.</p>

	{#if relief.processes.length}
		<ul class="processes">
			{#each relief.processes as p (p.process)}
				<li>
					<strong>{p.process}</strong>
					<span>{p.runs_finished} {p.runs_finished === 1 ? 'run' : 'runs'} finished</span>
					<span>
						{p.minutes_by_hand === null || p.minutes_by_hand === undefined
							? 'minutes by hand not stated'
							: `${p.minutes_by_hand} min by hand a case`}
					</span>
					<span class="hours">{regained(p.hours_regained)} regained</span>
					<a href={surfaceHref(p.takeover)}>Takeover instructions</a>
				</li>
			{/each}
		</ul>
	{/if}

	{#if relief.goals.length}
		<h3>Your goals</h3>
		<ul class="goals">
			{#each relief.goals as g (g.title)}
				<li data-reached={g.reached}>{goalLine(g)}</li>
			{/each}
		</ul>
	{/if}

	<form class="settings" onsubmit={save}>
		<h3>Your settings</h3>
		<label for="relief-roles">Share it with these roles (separated by commas; empty shares it with nobody)</label>
		<input id="relief-roles" bind:value={roles} autocomplete="off" />
		<fieldset>
			<legend>Your goals: hours a week Taktus takes off you</legend>
			{#each goals as g, i (i)}
				<div class="goal">
					<input aria-label={`Goal ${i + 1}`} bind:value={g.title} placeholder="for example: Friday afternoon free" />
					<input aria-label={`Hours a week for goal ${i + 1}`} type="number" min="0" step="0.5" bind:value={g.hours} />
				</div>
			{/each}
			<button type="button" class="quiet" onclick={() => (goals = [...goals, { title: '', hours: '' }])}>Add a goal</button>
		</fieldset>
		<label for="relief-line">A line in your channel</label>
		<select id="relief-line" bind:value={line}>
			{#each LINES as l (l.id)}<option value={l.id}>{l.label}</option>{/each}
		</select>
		{#if invalid}<p role="alert">{invalid}</p>{/if}
		{#if problem}<p role="alert">{problem}</p>{/if}
		{#if said}<p aria-live="polite">{said}</p>{/if}
		<button type="submit" disabled={busy}>Save</button>
	</form>

	<section class="text" aria-label="What Taktus took off you, as text">
		<h3>As text</h3>
		<ol>
			<li>{relief.sentence}</li>
			{#each relief.processes as p (p.process)}<li>{reliefLine(p)}</li>{/each}
			{#each relief.goals as g (g.title)}<li>{goalLine(g)}</li>{/each}
		</ol>
	</section>
</section>

<style>
	.private {
		display: inline-block;
		font-size: var(--fs-075);
		padding: var(--sp-050) var(--sp-150);
		border-radius: 999px;
		border: var(--bw-hairline) solid var(--border-subtle);
		color: var(--text-secondary);
	}
	ul {
		list-style: none;
		padding: 0;
		max-width: 48rem;
	}
	.processes li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-050) var(--sp-200);
		padding: var(--sp-100) 0;
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
	}
	.hours {
		font-variant-numeric: tabular-nums;
	}
	.goals li {
		padding: var(--sp-050) 0;
	}
	.settings {
		display: flex;
		flex-direction: column;
		gap: var(--sp-100);
		max-width: 32rem;
		margin-top: var(--sp-300);
	}
	label,
	legend {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
	fieldset {
		border: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: var(--sp-100);
	}
	.goal {
		display: flex;
		gap: var(--sp-100);
	}
	.goal input:first-child {
		flex: 1;
	}
	.goal input[type='number'] {
		width: 6rem;
	}
	.settings button {
		align-self: flex-start;
	}
</style>
