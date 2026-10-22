<!--
	The instance's tenants: `GET`, `POST` and `PATCH /administration/tenants` (ADR-0104), with the
	instance's administration key. That key is not an account key: it is asked for here, kept for
	the tab's session only, and sent in `Authorization: Bearer` and nowhere else.
-->
<script lang="ts">
	import { readAs, surface } from '../../lib/api';
	import {
		currentAdministrationKey,
		keepAdministrationKey,
		writeTenant,
		type Tenant
	} from '../../lib/governance';
	import TenantsView from '../../lib/TenantsView.svelte';

	let key = $state(currentAdministrationKey());
	let given = $state('');
	let refused: string | null = $state(null);
	let tenants: Tenant[] | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);

	function refuse(status: number, detail: string) {
		refused = detail;
		if (status === 401) {
			keepAdministrationKey('');
			key = null;
		}
	}

	async function load() {
		if (!key) return;
		const found = await readAs<{ tenants: Tenant[] }>(surface(location.href), 'administration/tenants', key);
		if (found.ok) tenants = found.body.tenants;
		else refuse(found.problem.status, found.problem.detail || found.problem.title);
	}

	$effect(() => {
		if (key) void load();
	});

	async function write(name: string, id: string | null) {
		if (!key) return;
		busy = true;
		const done = await writeTenant(surface(location.href), key, name, id);
		busy = false;
		if (done.ok) message = id === null ? `Created ${done.body.id}, named “${done.body.name}”.` : `Renamed ${done.body.id}.`;
		else message = done.problem.detail || done.problem.title;
		await load();
	}
</script>

{#if !key}
	<form
		class="key"
		onsubmit={(e) => {
			e.preventDefault();
			keepAdministrationKey(given);
			key = given.trim() || null;
			given = '';
			refused = null;
		}}
	>
		<p class="eyebrow">Tenants</p>
		{#if refused}<p role="alert">{refused}</p>{/if}
		<label>
			The instance's administration key
			<input type="password" autocomplete="off" bind:value={given} required />
		</label>
		<button type="submit">Read</button>
		<p class="hint">Not an account key. Kept for this browser tab only, and sent to this instance and nowhere else.</p>
	</form>
{:else if tenants}
	<TenantsView {tenants} {message} {busy} onCreate={(name) => write(name, null)} onRename={(id, name) => write(name, id)} />
{:else if refused}
	<p role="alert">{refused}</p>
{:else}
	<p class="status">Reading the tenants…</p>
{/if}

<style>
	.status,
	.hint {
		color: var(--muted);
		font-size: 0.9rem;
	}
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
		flex-basis: 100%;
	}
	.key {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: end;
		max-width: 36rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1 1 16rem;
	}
	input,
	button {
		font: inherit;
		padding: 0.4rem 0.6rem;
	}
	.hint {
		flex-basis: 100%;
		margin: 0;
	}
</style>
