<!--
	Each process's level, why it is there, and its correction rates (UC-7.5, ADR-0110, ADR-0122).
	It opens with the surface's sentence. Each process is an organ: the level in force, the level
	its version states and why, the incident that lowered it where a rule did, and one row per
	unit — the process, or one action class of it — with its rates over 7 and 28 days against the
	tenant's limit. Every figure is the surface's. None names a person (principle 14, ADR-0015).
	Written out below as its text equivalent.
-->
<script lang="ts">
	import type { AutonomyAnswer, RateWindow } from './governance';
	import { processLink, runLink } from './links';

	let { answer }: { answer: AutonomyAnswer } = $props();

	const limit = $derived(answer.limits.lower_rate);

	function percent(share: number): string {
		return `${Math.round(share * 100)} %`;
	}

	function figure(w: RateWindow): string {
		if (w.rate === null) return `nothing decided in ${w.days} days`;
		return `${w.corrected + w.rejected} of ${w.decided} changed · ${percent(w.rate)}`;
	}
</script>

<section class="autonomy" aria-labelledby="autonomy-title">
	<p class="eyebrow">Levels and corrections</p>
	<h1 id="autonomy-title">{answer.summary}</h1>
	<p class="private" data-private>Counted per process and action. No figure names a person.</p>

	<ul class="organs">
		{#each answer.processes as p (p.id)}
			<li class="organ" class:lowered={p.in_force < p.stated.level} data-process={p.id}>
				<div class="head">
					<a href={processLink(`${p.id}@${p.version}`)}>{p.name}</a>
					<span class="level" data-level={p.in_force} title="Autonomy level in force">L{p.in_force}</span>
				</div>
				<p>{p.text}</p>
				<p class="muted">{p.stated_text}</p>
				{#each p.lowerings as l (l.incident)}
					<p class="fell" data-lowering={l.incident}>
						Fell from {l.level_before} to {l.level_after} by the rule <code>{l.rule}</code>
						{#if l.run}in run <a href={runLink(l.run)}>{l.run}</a>{/if}, {l.raised_at.slice(0, 10)}.
					</p>
				{/each}
				{#if p.units.length}
				<table>
					<thead>
						<tr><th scope="col">Unit</th><th scope="col">Level</th><th scope="col">7 days</th><th scope="col">28 days</th></tr>
					</thead>
					<tbody>
						{#each p.units as u (u.action ?? '')}
							<tr data-unit={u.action ?? 'process'}>
								<th scope="row">{u.action ?? 'the process'}</th>
								<td>L{u.level}</td>
								{#each [u.week, u.month] as w (w.days)}
									<td>
										<span class="meter" aria-hidden="true">
											{#if w.rate !== null}
												<span class="fill" class:over={w.rate > limit} style="width: {Math.min(100, w.rate * 100)}%"></span>
											{/if}
											<span class="limit" style="left: {limit * 100}%"></span>
										</span>
										<span class="figure">{figure(w)}</span>
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
				{:else}
					<p class="muted">No proposal of it was decided by a person yet.</p>
				{/if}
				{#each p.raises_proposed as r (`${r.action}:${r.at}`)}
					<p class="raise" data-raise={r.action ?? 'process'}>
						Taktus proposes a raise of {r.action ?? 'the process'}: {figure(r.week)} over 7 days, {figure(r.month)} over 28. A person decides.
					</p>
				{/each}
			</li>
		{/each}
	</ul>

	<p class="muted limits">
		A unit falls one level above {percent(answer.limits.lower_rate)} over {answer.limits.lower_window_days} days, with at least
		{answer.limits.lower_minimum} decisions. A raise is proposed below {percent(answer.limits.raise_rate)} over 7 and 28 days, after
		{answer.limits.raise_decisions} decisions over {answer.limits.raise_weeks} weeks.
		{answer.limits.shipped_default ? 'These are the shipped limits.' : 'The tenant set these limits.'}
	</p>

	<section class="text" aria-label="Levels and corrections as text">
		<h2>As text</h2>
		<ol>
			<li>{answer.summary}</li>
			{#each answer.processes as p (p.id)}
				<li data-text="process:{p.id}">{p.name}: {p.text}</li>
				{#each p.units as u (u.action ?? '')}
					<li data-text="unit:{p.id}:{u.action ?? 'process'}">{u.text}</li>
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
		max-width: 28ch;
	}
	.private {
		display: inline-block;
		font-size: 0.85rem;
		padding: 0.3rem 0.8rem;
		border-radius: 999px;
		border: 1px solid var(--line);
		color: var(--ink-2);
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.88rem;
	}
	.organs {
		list-style: none;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(22rem, 1fr));
		gap: 0.9rem;
		margin-top: 1.5rem;
	}
	.organ {
		border-radius: 28px;
		padding: 1.1rem 1.25rem 1rem;
		background:
			radial-gradient(80% 90% at 30% 20%, color-mix(in oklch, var(--reproducible) 4%, transparent), transparent 70%),
			var(--paper-2);
		min-width: 0;
	}
	/* A level that fell by rule: an outline, so the distinction does not rest on colour. */
	.organ.lowered {
		box-shadow: inset 0 0 0 1.5px var(--alert);
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		font-weight: 600;
	}
	.head a {
		text-decoration: none;
	}
	.level {
		font-family: var(--mono);
		font-size: 0.72rem;
		font-weight: 400;
		border: 1px solid var(--line);
		border-radius: 6px;
		padding: 0 0.35rem;
	}
	.fell,
	.raise {
		font-size: 0.88rem;
		border-left: 3px solid var(--ink);
		padding-left: 0.6rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.82rem;
		margin-top: 0.5rem;
	}
	th,
	td {
		text-align: left;
		padding: 0.35rem 0.4rem 0.35rem 0;
		border-top: 1px solid var(--line);
		vertical-align: top;
		font-weight: 400;
	}
	thead th {
		color: var(--ink-3);
		border-top: none;
	}
	.meter {
		position: relative;
		display: block;
		height: 6px;
		border-radius: 3px;
		background: var(--paper);
		margin: 0.2rem 0;
		overflow: visible;
	}
	.fill {
		position: absolute;
		inset: 0 auto 0 0;
		border-radius: 3px;
		background: var(--ink-2);
	}
	.fill.over {
		background: var(--alert);
	}
	.limit {
		position: absolute;
		top: -3px;
		bottom: -3px;
		width: 1.5px;
		background: var(--ink);
	}
	.figure {
		color: var(--ink-2);
	}
	.limits {
		max-width: 46rem;
		margin-top: 1.5rem;
	}
</style>
