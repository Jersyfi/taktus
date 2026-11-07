<!--
	The organisation's structure (UC-1.4, ADR-0275), its projects (UC-1.6, ADR-0276) and a session
	in one of them (UC-1.8, ADR-0277). The tree in the levels the organisation named, with what is
	placed in each unit the reader may see; the reader's projects, created for a circle; and the
	reader's session in a project, every statement with its source. Shaping the structure is
	offered to everyone and refused by the surface where the reader's roles do not hold the right.
	The page computes nothing.
-->
<script lang="ts">
	import type { Session, Structure, Unit } from './workspace';
	import { levelName, tree } from './workspace';

	let {
		structure,
		projects = [],
		session = null,
		busy = false,
		message = null,
		onAddUnit,
		onPlace,
		onLevels,
		onKnowledge,
		onWhere,
		onCreateProject,
		onOpenSession,
		onSay,
		onPlan
	}: {
		structure: Structure;
		projects?: Unit[];
		session?: Session | null;
		busy?: boolean;
		message?: string | null;
		onAddUnit: (id: string, name: string, parent: string) => void;
		onPlace: (kind: string, name: string, unit: string) => void;
		onLevels: (levels: string[]) => void;
		onKnowledge: (unit: string, base: string) => void;
		onWhere: (kind: string, name: string) => void;
		onCreateProject: (id: string, name: string, circle: string, unit: string) => void;
		onOpenSession: (project: string) => void;
		onSay: (text: string) => void;
		onPlan: (goal: string) => void;
	} = $props();

	const KINDS = ['process', 'agent', 'connector', 'model', 'skill', 'budget'];
	let said = $state('');

	function form(handler: (data: FormData) => void) {
		return (event: SubmitEvent) => {
			event.preventDefault();
			const target = event.currentTarget as HTMLFormElement;
			handler(new FormData(target));
			target.reset();
		};
	}
	const text = (data: FormData, name: string) => String(data.get(name) ?? '').trim();
	const placed = (unit: string) => structure.placements.filter((p) => p.unit === unit);
</script>

<section class="structure" aria-labelledby="structure-title">
	<p class="eyebrow">Structure · {structure.levels.join(' → ')}</p>
	<h1 id="structure-title">Where things belong</h1>
	<p class="muted">
		What is placed in a unit is seen there and in the units below it, uses what is shared there and above it,
		and its cost counts there and above. A private project is yours alone.
	</p>
	{#if message}<p class="message" aria-live="polite">{message}</p>{/if}

	<ul class="tree" aria-label="Units">
		{#each tree(structure.units) as { unit, depth } (unit.id)}
			<li style:--depth={depth} data-unit={unit.id}>
				<strong>{unit.name}</strong>
				<span class="muted">{levelName(structure, unit)}{unit.private ? ' · private' : ''}{structure.yours.includes(unit.id) ? ' · yours' : ''}</span>
				{#each placed(unit.id) as p (`${p.kind}:${p.object}`)}
					<span class="chip">{p.kind}: {p.object}</span>
				{/each}
			</li>
		{/each}
	</ul>

	<h2>Your projects</h2>
	{#if projects.length === 0}<p class="muted" data-empty>No project yet.</p>{/if}
	<ul class="projects">
		{#each projects as p (p.id)}
			<li>
				{p.name} <span class="muted">· {p.circle}</span>
				{#each p.references ?? [] as r (r.link)}<a href={r.link}>{r.title || r.kind}</a>{/each}
				<button type="button" class="quiet" disabled={busy} onclick={() => onOpenSession(p.id)}>Think it through</button>
			</li>
		{/each}
	</ul>
	<form data-act="project.create" onsubmit={form((d) => onCreateProject(text(d, 'id'), text(d, 'name'), text(d, 'circle'), text(d, 'unit')))}>
		<label>Project name (lower case) <input name="id" required /></label>
		<label>Title <input name="name" required /></label>
		<label>
			For
			<select name="circle">
				<option value="alone">me alone (private)</option>
				<option value="team">my team</option>
				<option value="project_team">a project team</option>
				<option value="company">the whole company</option>
			</select>
		</label>
		<label>Team or unit (for a team) <input name="unit" /></label>
		<button type="submit" disabled={busy}>Create project</button>
	</form>

	{#if session}
		<section class="session" aria-label="Session" data-session={session.id}>
			<h2>Session in {session.project}</h2>
			<ol class="turns">
				{#each session.turns ?? [] as turn, i (i)}
					<li class={turn.speaker}>
						{#if turn.speaker === 'participant'}{turn.text}{:else}
							{#each turn.statements ?? [] as s, j (j)}
								<p>
									{s.text}
									{#if s.source}<a class="source" href={s.source.link}>{s.source.title}</a>{:else}<span class="muted"> (not drawn from the project's knowledge)</span>{/if}
								</p>
							{/each}
						{/if}
					</li>
				{/each}
			</ol>
			<form onsubmit={(e) => { e.preventDefault(); onSay(said); said = ''; }}>
				<label>Say <input bind:value={said} /></label>
				<button type="submit" disabled={busy || !said.trim()}>Send</button>
			</form>
			<form onsubmit={form((d) => onPlan(text(d, 'goal')))}>
				<label>Settle it in a plan: the goal <input name="goal" required /></label>
				<button type="submit" disabled={busy}>Make it a plan</button>
			</form>
		</section>
	{/if}

	<h2>Shape the structure</h2>
	<div class="shape">
		<form data-act="structure.levels" onsubmit={form((d) => onLevels(text(d, 'levels').split(',').map((s) => s.trim())))}>
			<label>Levels, the root's first, by commas <input name="levels" required placeholder={structure.levels.join(', ')} /></label>
			<button type="submit" disabled={busy}>Name the levels</button>
		</form>
		<form data-act="structure.unit" onsubmit={form((d) => onAddUnit(text(d, 'id'), text(d, 'name'), text(d, 'parent')))}>
			<label>Unit (lower case) <input name="id" required /></label>
			<label>Its name <input name="name" required /></label>
			<label>Below <input name="parent" required /></label>
			<button type="submit" disabled={busy}>Add unit</button>
		</form>
		<form data-act="structure.place" onsubmit={form((d) => onPlace(text(d, 'kind'), text(d, 'name'), text(d, 'unit')))}>
			<label>What <select name="kind">{#each KINDS as k (k)}<option value={k}>{k}</option>{/each}</select></label>
			<label>Its name <input name="name" required /></label>
			<label>Into unit <input name="unit" required /></label>
			<button type="submit" disabled={busy}>Place or move</button>
		</form>
		<form data-act="structure.knowledge" onsubmit={form((d) => onKnowledge(text(d, 'unit'), text(d, 'base')))}>
			<label>Unit <input name="unit" required /></label>
			<label>Its knowledge system, the link <input name="base" required /></label>
			<button type="submit" disabled={busy}>Configure</button>
		</form>
		<form data-act="structure.where" onsubmit={form((d) => onWhere(text(d, 'kind'), text(d, 'name')))}>
			<label>What <select name="kind">{#each KINDS as k (k)}<option value={k}>{k}</option>{/each}</select></label>
			<label>Its name <input name="name" required /></label>
			<button type="submit" disabled={busy}>Where is it documented?</button>
		</form>
	</div>
	<span hidden data-act="structure.show"></span>
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.tree,
	.projects,
	.turns {
		list-style: none;
		padding: 0;
		display: grid;
		gap: var(--sp-100);
	}
	.tree li {
		padding-inline-start: calc(var(--depth, 0) * var(--sp-300));
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-100);
		align-items: baseline;
	}
	.chip {
		font-size: var(--fs-075);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-radius: var(--r-lg);
		padding: 0 var(--sp-100);
	}
	.shape {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
		gap: var(--sp-250);
	}
	form {
		display: grid;
		gap: var(--sp-100);
		margin-top: var(--sp-150);
	}
	label {
		display: grid;
		gap: var(--sp-050);
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
	}
	.turns .taktus {
		border-inline-start: 3px solid var(--accent-primary);
		padding-inline-start: var(--sp-150);
	}
	.source {
		font-size: var(--fs-075);
		margin-inline-start: var(--sp-100);
	}
	.message {
		background: var(--status-info-surface);
		color: var(--status-info-text);
		border: var(--bw-hairline) solid var(--status-info-border);
		border-radius: var(--r-lg);
		padding: var(--sp-150) var(--sp-200);
	}
</style>
