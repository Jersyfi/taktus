<!--
	The instance's health (ADR-0295, UC-10.2): the release it runs, whether it may receive traffic
	and why not, the roles it serves, and the tenant's backup, alerts and incidents. Below it, an
	update of Taktus prepared as a plan: the form opens a plan draft, which the reader works out
	and commissions in the plan dialogue. Commissioning applies nothing; a person carries the
	steps out (ADR-0296, ADR-0013 D).
-->
<script lang="ts">
	import type { Health } from './operation';

	let {
		health,
		message = null,
		busy = false,
		onPrepare
	}: {
		health: Health;
		message?: string | null;
		busy?: boolean;
		onPrepare: (to: string, said: string) => void;
	} = $props();

	let to = $state('');
	let said = $state('');
	const RELEASE = /^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$/;
	const valid = $derived(RELEASE.test(to.trim()));
	const sentence = $derived(
		health.ready
			? `Taktus ${health.release} is ready.`
			: `Taktus ${health.release} is not ready: ${health.reason ?? 'no reason given'}.`
	);
</script>

<section class="health" aria-labelledby="health-title">
	<p class="eyebrow">Health</p>
	<h1 id="health-title">{sentence}</h1>
	<dl class="facts" data-act="instance.health">
		<dt>Release</dt><dd>{health.release}</dd>
		<dt>Ready</dt><dd>{health.ready ? 'yes' : `no: ${health.reason}`}</dd>
		<dt>Roles</dt><dd>{health.roles.join(', ') || 'none'}{health.leading ? ', leading' : ''}</dd>
		<dt>Backup</dt><dd><a href="#/backup">{health.backup.replace('_', ' ')}</a></dd>
		<dt>Alerts</dt><dd><a href="#/alerts">{health.alerts_in_effect} in effect</a></dd>
		<dt>Incidents</dt><dd><a href="#/incidents">{health.incidents_open} open</a></dd>
	</dl>

	<h2>Prepare an update</h2>
	<p class="muted">
		Taktus prepares the update as a plan: a backup, the upgrade and the check, each a person's step,
		with the way back to the release before. You commission it in the plan dialogue; commissioning
		applies nothing, and a person carries the steps out.
	</p>
	{#if message}<p class="message" role="status">{message}</p>{/if}
	<form
		data-act="instance.update"
		onsubmit={(e) => {
			e.preventDefault();
			if (valid) onPrepare(to.trim(), said.trim());
		}}
	>
		<label>The release to update to <input type="text" placeholder="1.0.1" bind:value={to} autocomplete="off" /></label>
		<label>Why <input type="text" bind:value={said} autocomplete="off" /></label>
		<button type="submit" disabled={busy || !valid}>Prepare the plan</button>
	</form>
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: 0.88rem;
		max-width: 44rem;
	}
	.facts {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.35rem 1rem;
		max-width: 44rem;
	}
	dt {
		color: var(--text-secondary);
	}
	dd {
		margin: 0;
	}
	form {
		display: flex;
		gap: 0.5rem;
		align-items: end;
		flex-wrap: wrap;
		max-width: 44rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.88rem;
	}
	input {
		font: inherit;
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--border-subtle);
		border-radius: 10px;
		background: var(--bg-canvas);
		color: var(--text-primary);
	}
	.message {
		background: var(--bg-surface);
		border-radius: 14px;
		padding: 0.8rem 1rem;
		max-width: 44rem;
	}
</style>
