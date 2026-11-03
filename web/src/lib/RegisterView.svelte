<!--
	Everything that acts for the tenant (UC-7.8, ADR-0147 §2). It opens with the surface's
	sentence. Each adapter is a card: what it serves, a ladder of the five autonomy levels with
	the highest it acts at, the strongest exactness it produces, its removal verdict as a chip,
	where it processes against the residency rule, and what it used. Cards that need attention
	come first and say why. The stop is a person's act: it names what it halts and is confirmed
	once, then ADR-0138's rule halts every run at its boundary. No card names a person.
-->
<script lang="ts">
	import { usedText, type Register, type RegisterRow } from './acting';
	import { processLink, removeLink } from './links';

	let {
		register,
		onStop,
		onInventory
	}: {
		register: Register;
		onStop?: (adapter: string) => Promise<string | null>;
		onInventory?: () => void;
	} = $props();

	let asking: string | null = $state(null);
	let said: Record<string, string> = $state({});
	let onlyAttention = $state(false);

	const shown = $derived(onlyAttention ? register.rows.filter((r) => r.attention.length) : register.rows);
	const needing = $derived(register.rows.filter((r) => r.attention.length).length);

	async function stop(row: RegisterRow) {
		if (!onStop) return;
		const problem = await onStop(row.adapter);
		said[row.adapter] = problem ?? `Stop of ${row.adapter} requested: every run it serves halts at its next step boundary.`;
		asking = null;
	}
</script>

<section class="register" aria-labelledby="register-title">
	<p class="eyebrow">What acts for us</p>
	<h1 id="register-title">{register.summary}</h1>
	<p class="private" data-private>Adapters, steps and runs only. No row names a person.</p>

	<div class="tools">
		<label><input type="checkbox" bind:checked={onlyAttention} /> Only what needs attention ({needing})</label>
		<a href={removeLink()}>Where data goes</a>
		{#if onInventory}
			<button type="button" class="quiet" onclick={onInventory}>AI inventory (not legally reviewed)</button>
		{/if}
	</div>

	<ul class="cards">
		{#each shown as row (row.adapter)}
			<li class="card" class:attention={row.attention.length > 0} class:stopped={row.stopped} data-adapter={row.adapter}>
				<div class="head">
					<span class="family">{row.family}</span>
					<strong>{row.adapter}</strong>
					{#if row.removal}
						<span class="chip {row.removal.verdict}" title="Last removal test, {row.removal.tested_at.slice(0, 10)}"
							>{row.removal.verdict}</span
						>
					{:else}
						<span class="chip untested" title="Never removal-tested">untested</span>
					{/if}
				</div>
				<div class="ladder" aria-label={row.level === undefined ? 'No process uses it' : `Acts up to level ${row.level}`}>
					{#each [0, 1, 2, 3, 4] as l (l)}
						<span class="rung" class:on={row.level !== undefined && l <= row.level}></span>
					{/each}
					<span class="muted">{row.level === undefined ? 'unused' : `L${row.level}`}{row.exactness ? ` · ${row.exactness}` : ''}</span>
				</div>
				{#if row.attention.length}
					<ul class="reasons">
						{#each row.attention as reason (reason)}<li>{reason}</li>{/each}
					</ul>
				{/if}
				<p class="muted">
					{row.serves.join(', ') || 'serves nothing declared'} · {row.location ?? 'location undeclared'}
					<span class="residency {row.residency}">{row.residency === 'outside' ? 'outside the rule' : row.residency}</span>
				</p>
				{#if row.processes.length}
					<p class="uses">
						In
						{#each row.processes as p, i (p)}{#if i > 0}, {/if}<a href={processLink(p)}>{p}</a>{/each}
						· <a href={removeLink(row.adapter)}>if it goes</a>
					</p>
				{/if}
				<p class="muted">{usedText(row.used)}</p>
				<div class="stop">
					{#if row.stopped}
						<span class="held">A stop is held.</span>
					{:else if asking === row.adapter}
						<span>Every run on {row.adapter} halts at its next step boundary{row.processes.length ? ` (${row.processes.join(', ')})` : ''}.</span>
						<button type="button" class="danger" onclick={() => stop(row)}>Stop {row.adapter}</button>
						<button type="button" class="quiet" onclick={() => (asking = null)}>Keep it running</button>
					{:else if onStop}
						<button type="button" class="quiet" onclick={() => (asking = row.adapter)}>Stop…</button>
					{/if}
					{#if said[row.adapter]}<p role="status">{said[row.adapter]}</p>{/if}
				</div>
			</li>
		{/each}
	</ul>

	<section class="text" aria-label="The register as text">
		<h2>As text</h2>
		<ol>
			<li>{register.summary}</li>
			{#each register.rows as row (row.adapter)}
				<li data-text="adapter:{row.adapter}">{row.text}</li>
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
		max-width: 30ch;
	}
	.private {
		display: inline-block;
		font-size: 0.85rem;
		padding: 0.3rem 0.8rem;
		border-radius: 999px;
		border: 1px solid var(--line);
		color: var(--ink-2);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		align-items: center;
		margin: 1rem 0;
		font-size: 0.9rem;
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.86rem;
		margin: 0.3rem 0;
	}
	.cards {
		list-style: none;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 21rem), 1fr));
		gap: 0.9rem;
	}
	.card {
		border-radius: 24px;
		padding: 1rem 1.15rem;
		background: var(--paper-2);
		min-width: 0;
	}
	/* What needs attention carries an outline, so the distinction does not rest on colour. */
	.card.attention {
		box-shadow: inset 0 0 0 1.5px var(--alert);
	}
	.card.stopped {
		background: repeating-linear-gradient(135deg, var(--paper-2) 0 10px, var(--paper) 10px 20px);
	}
	.head {
		display: flex;
		gap: 0.5rem;
		align-items: baseline;
		flex-wrap: wrap;
	}
	.family {
		font-family: var(--mono);
		font-size: 0.72rem;
		color: var(--ink-3);
	}
	.chip {
		margin-left: auto;
		font-size: 0.72rem;
		border-radius: 999px;
		padding: 0 0.55rem;
		border: 1px solid var(--line);
	}
	.chip.broke {
		border-color: var(--alert);
		color: var(--alert);
	}
	.chip.changed {
		border-color: var(--person);
		color: var(--person);
	}
	.chip.untested {
		border-style: dashed;
	}
	.ladder {
		display: flex;
		gap: 3px;
		align-items: center;
		margin: 0.5rem 0;
	}
	.rung {
		width: 18px;
		height: 6px;
		border-radius: 3px;
		background: var(--line);
	}
	.rung.on {
		background: var(--reproducible);
	}
	.reasons {
		margin: 0.4rem 0;
		padding-left: 1rem;
		font-size: 0.86rem;
	}
	.residency.outside {
		color: var(--alert);
		font-weight: 600;
	}
	.uses {
		font-size: 0.88rem;
		margin: 0.3rem 0;
	}
	.stop {
		margin-top: 0.5rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
		font-size: 0.86rem;
	}
	button {
		font: inherit;
		border-radius: 999px;
		padding: 0.2rem 0.8rem;
		border: 1px solid var(--line);
		background: var(--paper);
		color: var(--ink);
		cursor: pointer;
	}
	button.danger {
		border-color: var(--alert);
		color: var(--alert);
	}
	.held {
		color: var(--alert);
	}
	a {
		color: inherit;
	}
</style>
