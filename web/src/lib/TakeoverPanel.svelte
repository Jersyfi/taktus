<!--
	Taking over a running step, and handing its result back (UC-4.19, ADR-0128). A running worker
	step offers "take over"; the ask is read back before it is sent. Once the runner served it, the
	page shows what the step reached — its goal, acceptance criteria and inputs, the worker's
	checkpoint and what it produced — and until when the person holds it. The result is read back
	before it is handed back: nothing takes effect before the reader confirms it (ADR-0008). A
	lapsed or refused take-over is said as such. No person is named here (principle 14).
-->
<script lang="ts">
	import { described, leaseLeft, leasePassed, offered, readResult, sentence, served, standingOf, type Asked, type Reading } from './takeover';
	import type { RunLevel, StepElement, TakeoverState } from './types';

	let {
		level,
		asked = null,
		states = {},
		message = null,
		busy = false,
		now = new Date(),
		onTakeOver,
		onHandBack
	}: {
		level: RunLevel;
		/** The take-over this reader asked for in this tab, if any. */
		asked?: Asked | null;
		/** The state of each held take-over, by its identifier, as the surface answered it. */
		states?: Record<string, TakeoverState>;
		/** What the surface said after the last act. */
		message?: string | null;
		busy?: boolean;
		now?: Date;
		onTakeOver: (step: string) => void;
		onHandBack: (takeover: string, result: unknown) => void;
	} = $props();

	const offers = $derived(offered(level));
	const taken = $derived(served(level));
	const mine = $derived(asked ? standingOf(level, asked) : null);
	/** Shown apart only while it is not on a step yet: asked, or refused. */
	const pending = $derived(asked && (mine === 'asked' || mine === 'refused') ? asked : null);

	let confirming: string | null = $state(null);
	let written: Record<string, string> = $state({});
	let reading: Record<string, Reading | null> = $state({});

	function readBack(takeover: string, event: SubmitEvent) {
		event.preventDefault();
		reading[takeover] = readResult(written[takeover] ?? '');
	}

	function handBack(takeover: string) {
		const found = reading[takeover];
		if (!found) return;
		onHandBack(takeover, found.value);
		reading[takeover] = null;
	}

	function pretty(value: unknown): string {
		return JSON.stringify(value, null, 2) ?? 'null';
	}

	function short(digest: string): string {
		const [algorithm, hex] = digest.split(':');
		return hex ? `${algorithm}:${hex.slice(0, 12)}…` : digest;
	}

	function since(step: StepElement): string | undefined {
		return step.wait?.cause === 'taken_over' ? step.wait.since : undefined;
	}
</script>

{#if offers.length || taken.length || pending || message}
	<section class="takeover" aria-labelledby="takeover-title">
		<h2 id="takeover-title">Take over</h2>

		{#if message}
			<p class="said" aria-live="polite">{message}</p>
		{/if}

		{#if pending && mine}
			<div class="card" data-takeover={pending.takeover} data-standing={mine}>
				<p class="eyebrow">{pending.takeover} · {pending.step}</p>
				<p>{sentence(mine, pending.step)}</p>
			</div>
		{/if}

		{#each taken as step (step.id)}
			{@const t = step.takeover!}
			{@const state = states[t.id]}
			<article class="card" class:held={t.standing === 'held'} data-takeover={t.id} data-standing={t.standing}>
				<p class="eyebrow">{t.id} · {step.id} · {t.standing.replace('_', ' ')}</p>
				<p>{sentence(t.standing, step.id)}</p>

				{#if t.standing === 'held' && t.until}
					<div class="lease">
						<p class="muted" data-lease={t.until}>Held {leaseLeft(t.until, now)}.</p>
						<div
							class="bar"
							role="meter"
							aria-label="How much of the take-over's time has passed"
							aria-valuemin="0"
							aria-valuemax="100"
							aria-valuenow={Math.round(leasePassed(since(step), t.until, now) * 100)}
						>
							<span style:width={`${leasePassed(since(step), t.until, now) * 100}%`}></span>
						</div>
					</div>

					{#if state}
						<dl class="state" data-state={state.takeover}>
							<dt>Goal</dt>
							<dd>{state.goal ?? 'The step names none.'}</dd>
							<dt>Acceptance criteria</dt>
							<dd>
								{#if state.acceptance.length}
									<ul>
										{#each state.acceptance as criterion, i (i)}<li>{criterion}</li>{/each}
									</ul>
								{:else}None named.{/if}
							</dd>
							<dt>Inputs, as the worker received them</dt>
							<dd><pre>{pretty(state.inputs)}</pre></dd>
							{#if state.credentials.length}
								<dt>Credentials, by parameter</dt>
								<dd class="mono">{state.credentials.join(', ')}</dd>
							{/if}
							<dt>The worker's checkpoint</dt>
							<dd class="mono">{state.checkpoint ?? 'none yet'}</dd>
							<dt>Produced so far</dt>
							<dd>
								{#if state.artifacts.length}
									<table>
										<thead><tr><th>Artifact</th><th>Kind</th><th>Digest</th></tr></thead>
										<tbody>
											{#each state.artifacts as a (a.id)}
												<tr><td>{a.title ?? a.id}</td><td class="mono">{a.kind}</td><td class="mono" title={a.digest}>{short(a.digest)}</td></tr>
											{/each}
										</tbody>
									</table>
								{:else}Nothing yet.{/if}
							</dd>
						</dl>
					{:else}
						<p class="muted">Reading the state the step was taken over in…</p>
					{/if}

					<form class="result" onsubmit={(e) => readBack(t.id, e)}>
						<label>
							Your result — JSON, or plain text
							<textarea rows="5" bind:value={written[t.id]} spellcheck="false"></textarea>
						</label>
						<button type="submit" disabled={busy || !(written[t.id] ?? '').trim()}>Read it back</button>
					</form>
					{#if reading[t.id]}
						<div class="reading" aria-live="polite">
							<p>Your result is read {described(reading[t.id]!)}. It becomes the result of {step.id}, produced by a person; the run then continues.</p>
							<div class="row">
								<button type="button" class="primary" disabled={busy} onclick={() => handBack(t.id)}>Hand back as yours</button>
								<button type="button" disabled={busy} onclick={() => (reading[t.id] = null)}>Change it</button>
							</div>
							<p class="muted">Nothing is handed back before you confirm how your result was read.</p>
						</div>
					{/if}
				{/if}
			</article>
		{/each}

		{#if offers.length}
			<ul class="offers">
				{#each offers as step (step.id)}
					<li data-offer={step.id}>
						<div>
							<strong>{step.id}</strong>
							<span class="muted">a worker step, {step.state}</span>
						</div>
						{#if confirming === step.id}
							<div class="confirm">
								<p>
									You take over {step.id}. Its worker stops at its next boundary and hands you what it reached. The run then
									waits for you, until you hand the result back or the take-over's time runs out.
								</p>
								<div class="row">
									<button
										type="button"
										class="primary"
										disabled={busy}
										onclick={() => {
											confirming = null;
											onTakeOver(step.id);
										}}>Take over {step.id}</button
									>
									<button type="button" disabled={busy} onclick={() => (confirming = null)}>Cancel</button>
								</div>
							</div>
						{:else}
							<button type="button" disabled={busy} onclick={() => (confirming = step.id)}>Take over</button>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{/if}

<style>
	.takeover {
		margin-top: 2rem;
		max-width: 52rem;
	}
	.eyebrow {
		font-family: var(--mono);
		font-size: 0.72rem;
		letter-spacing: 0.04em;
		color: var(--ink-3);
		margin: 0 0 0.35rem;
	}
	.muted {
		color: var(--ink-2);
	}
	.mono,
	pre {
		font-family: var(--mono);
		font-size: 0.82rem;
	}
	.said {
		background: var(--paper-2);
		border-radius: 12px;
		padding: 0.6rem 0.9rem;
	}
	.card {
		border: 1px solid var(--line);
		border-radius: 14px;
		padding: 0.9rem 1.1rem;
		margin: 0.6rem 0;
	}
	.card p {
		margin: 0.25rem 0;
	}
	/* A step a person holds carries the person family's hue: the one colour this page adds. */
	.card.held {
		border-color: var(--person);
		box-shadow: inset 3px 0 0 var(--person);
	}
	.card[data-standing='lapsed'],
	.card[data-standing='refused'] {
		border-style: dashed;
	}
	.lease {
		margin: 0.5rem 0 0.75rem;
	}
	.bar {
		height: 4px;
		border-radius: 2px;
		background: var(--paper-2);
		overflow: hidden;
	}
	.bar span {
		display: block;
		height: 100%;
		background: var(--person);
	}
	.state {
		display: grid;
		grid-template-columns: minmax(9rem, 14rem) 1fr;
		gap: 0.4rem 1rem;
		margin: 0.75rem 0;
	}
	.state dt {
		font-weight: 600;
	}
	.state dd {
		margin: 0;
		min-width: 0;
	}
	.state ul {
		margin: 0;
		padding-left: 1.1rem;
	}
	pre {
		margin: 0;
		background: var(--paper-2);
		border-radius: 10px;
		padding: 0.6rem 0.8rem;
		overflow-x: auto;
	}
	table {
		border-collapse: collapse;
		width: 100%;
		font-size: 0.88rem;
	}
	th,
	td {
		text-align: left;
		padding: 0.2rem 0.6rem 0.2rem 0;
		border-bottom: 1px solid var(--line);
	}
	th {
		font-weight: 500;
		color: var(--ink-2);
	}
	.result {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		margin-top: 0.75rem;
	}
	.result label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	textarea {
		font: inherit;
		font-family: var(--mono);
		font-size: 0.85rem;
		padding: 0.5rem 0.7rem;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: var(--paper);
		color: var(--ink);
		resize: vertical;
	}
	.reading,
	.confirm {
		background: var(--paper-2);
		border-radius: 12px;
		padding: 0.75rem 0.9rem;
		margin-top: 0.6rem;
	}
	.offers {
		list-style: none;
		padding: 0;
		display: grid;
		gap: 0.5rem;
	}
	.offers li {
		border: 1px solid var(--line);
		border-radius: 14px;
		padding: 0.7rem 1rem;
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
	}
	.offers .confirm {
		flex-basis: 100%;
	}
	.row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	button {
		font: inherit;
		border: 1px solid var(--line);
		background: var(--paper);
		color: var(--ink);
		border-radius: 10px;
		padding: 0.4rem 0.9rem;
		cursor: pointer;
		align-self: flex-start;
	}
	button.primary {
		background: var(--ink);
		color: var(--paper);
		border-color: var(--ink);
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	@media (max-width: 760px) {
		.state {
			grid-template-columns: 1fr;
		}
	}
</style>
