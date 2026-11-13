<!--
	The instance's tenants, for the holder of its administration key (ADR-0104, ADR-0122). Each
	with its identifier, which Taktus generated, its display name and when it was created. A new
	tenant and a new name are each said back before they are sent: Taktus generates the
	identifier, and the name is the only thing given. A tenant is exported to one file, and an
	export is imported into this instance and checked by its chains (ADR-0221, ADR-0295).
-->
<script lang="ts">
	import type { Tenant } from './governance';

	let {
		tenants,
		message = null,
		busy = false,
		onCreate,
		onRename,
		onExport = () => {},
		onImport = () => {}
	}: {
		tenants: Tenant[];
		message?: string | null;
		busy?: boolean;
		onCreate: (name: string) => void;
		onRename: (id: string, name: string) => void;
		onExport?: (id: string) => void;
		onImport?: (file: File) => void;
	} = $props();

	let chosen: File | null = $state(null);

	let name = $state('');
	let renaming: string | null = $state(null);
	let newName = $state('');
	type Pending = { act: 'create'; id: null } | { act: 'rename'; id: string };
	let pending = $state<Pending | null>(null);

	function sayBack(p: Pending | null): string {
		if (p === null) return '';
		if (p.act === 'create') return `A new tenant named “${name.trim()}”. Taktus generates its identifier.`;
		return `The tenant ${p.id} is named “${newName.trim()}” from now on; its identifier stays.`;
	}
	const said = $derived(sayBack(pending));

	function confirm() {
		if (pending?.act === 'create') onCreate(name.trim());
		else if (pending?.act === 'rename') onRename(pending.id, newName.trim());
		pending = null;
		name = '';
		renaming = null;
		newName = '';
	}
</script>

<section class="tenants" aria-labelledby="tenants-title">
	<p class="eyebrow">Tenants</p>
	<h1 id="tenants-title">This instance serves {tenants.length} {tenants.length === 1 ? 'tenant' : 'tenants'}.</h1>
	<p class="muted">For the holder of the instance's administration key. An account key is not admitted here.</p>
	{#if message}<p class="message" role="status">{message}</p>{/if}

	<ul class="list">
		{#each tenants as t (t.id)}
			<li data-tenant={t.id} data-act="tenant.list">
				<span class="id">{t.id}</span>
				<strong>{t.name}</strong>
				<span class="muted">since {t.created_at.slice(0, 10)}</span>
				{#if renaming === t.id}
					<form
						data-act="tenant.rename"
						onsubmit={(e) => {
							e.preventDefault();
							if (newName.trim()) pending = { act: 'rename', id: t.id };
						}}
					>
						<label>New name <input type="text" bind:value={newName} autocomplete="off" /></label>
						<button type="submit" disabled={busy || !newName.trim()}>Rename</button>
					</form>
				{:else}
					<button type="button" class="quiet" disabled={busy} onclick={() => (renaming = t.id)}>Rename</button>
				{/if}
				<button type="button" class="quiet" data-act="tenant.export" disabled={busy} onclick={() => onExport(t.id)}>Export</button>
			</li>
		{/each}
	</ul>

	<form
		class="create"
		data-act="tenant.create"
		onsubmit={(e) => {
			e.preventDefault();
			if (name.trim()) pending = { act: 'create', id: null };
		}}
	>
		<label>A new tenant's name <input type="text" bind:value={name} autocomplete="off" /></label>
		<button type="submit" disabled={busy || !name.trim()}>Create</button>
	</form>

	<form
		class="create"
		data-act="tenant.import"
		onsubmit={(e) => {
			e.preventDefault();
			if (chosen) onImport(chosen);
		}}
	>
		<label
			>An export to import, into a tenant this instance holds nothing of
			<input
				type="file"
				accept="application/json,.json"
				onchange={(e) => (chosen = (e.currentTarget as HTMLInputElement).files?.[0] ?? null)}
			/>
		</label>
		<button type="submit" disabled={busy || !chosen}>Import and check</button>
	</form>
	<p class="muted">An export holds the tenant's data and its identities' key digests: keep it as a backup is kept.</p>

	{#if pending}
		<div class="reading" aria-live="polite">
			<p>{said}</p>
			<button type="button" class="primary" disabled={busy} onclick={confirm}>Yes, do it</button>
			<button type="button" disabled={busy} onclick={() => (pending = null)}>No</button>
		</div>
	{/if}

	<section class="text" aria-label="The tenants as text">
		<h2>As text</h2>
		<ol>
			{#each tenants as t (t.id)}
				<li data-text="tenant:{t.id}">{t.id}: {t.name}, created {t.created_at.slice(0, 10)}.</li>
			{/each}
		</ol>
	</section>
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: 0.88rem;
	}
	.id {
		font-family: var(--font-mono);
		font-size: 0.78rem;
		color: var(--text-subtle);
	}
	.list {
		list-style: none;
		padding: 0;
		max-width: 46rem;
	}
	.list li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: baseline;
		padding: 0.6rem 0;
		border-bottom: 1px solid var(--border-subtle);
	}
	form {
		display: flex;
		gap: 0.5rem;
		align-items: end;
		flex-wrap: wrap;
	}
	.create {
		margin-top: 1.25rem;
		max-width: 46rem;
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
	.reading,
	.message {
		background: var(--bg-surface);
		border-radius: 14px;
		padding: 0.8rem 1rem;
		margin-top: 1rem;
		max-width: 46rem;
	}
</style>
