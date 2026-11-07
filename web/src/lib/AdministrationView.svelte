<!--
	A tenant's administration (UC-10.2, ADR-0279): every act the command line's `taktusctl identity`
	and `taktusctl units` offer, each a form marked with its act's name as the inventory names it
	(`data-act`). A key the surface answers is shown once and kept nowhere. Every act is refused by
	the surface where the reader's roles do not hold `tenant.administer`. The page computes nothing.
-->
<script lang="ts">
	let {
		links = [],
		rights = { roles: [], rights: [] },
		quotas = [],
		shownKey = null,
		busy = false,
		message = null,
		onAct
	}: {
		links?: { id: string; channel: string; identity: string; revoked_at?: string }[];
		rights?: { roles: { role: string; rights: string[] }[]; rights: string[] };
		quotas?: { org_unit: string; concurrent_runs?: number; budget?: Record<string, number> }[];
		shownKey?: string | null;
		busy?: boolean;
		message?: string | null;
		onAct: (act: string, values: Record<string, string>) => void;
	} = $props();

	function submit(act: string) {
		return (event: SubmitEvent) => {
			event.preventDefault();
			const target = event.currentTarget as HTMLFormElement;
			const values: Record<string, string> = {};
			for (const [k, v] of new FormData(target).entries()) values[k] = String(v).trim();
			onAct(act, values);
			target.reset();
		};
	}
</script>

<section class="administration" aria-labelledby="administration-title">
	<p class="eyebrow">Administration · this tenant</p>
	<h1 id="administration-title">People, rights and quotas</h1>
	<p class="muted">Every act here is recorded in the ledger with who did it. The command line offers each one too.</p>
	{#if message}<p class="message" aria-live="polite">{message}</p>{/if}
	{#if shownKey}
		<p class="key" data-key>Hand this key to the person once; it is kept nowhere: <code>{shownKey}</code></p>
	{/if}

	<div class="acts">
		<form data-act="identity.add" onsubmit={submit('identity.add')}>
			<h2>Add a person</h2>
			<label>Identity <input name="identity" required placeholder="idn_ada" /></label>
			<label>Units below the tenant, by commas <input name="org_path" /></label>
			<label>Roles, by commas <input name="roles" /></label>
			<button type="submit" disabled={busy}>Add</button>
		</form>
		<form data-act="identity.key" onsubmit={submit('identity.key')}>
			<h2>A new account key</h2>
			<label>Identity <input name="identity" required /></label>
			<button type="submit" disabled={busy}>Issue key</button>
		</form>
		<form data-act="identity.agent-key" onsubmit={submit('identity.agent-key')}>
			<h2>A new agent key</h2>
			<label>Identity <input name="identity" required /></label>
			<button type="submit" disabled={busy}>Issue agent key</button>
		</form>
		<form data-act="identity.roles" onsubmit={submit('identity.roles')}>
			<h2>Set roles</h2>
			<label>Identity <input name="identity" required /></label>
			<label>Roles, by commas — none clears <input name="roles" /></label>
			<button type="submit" disabled={busy}>Set</button>
		</form>
		<form data-act="identity.grant" onsubmit={submit('identity.grant')}>
			<h2>Grant a role a right</h2>
			<label>Role <input name="role" required /></label>
			<label>Right <select name="right">{#each rights.rights as r (r)}<option value={r}>{r}</option>{/each}</select></label>
			<button type="submit" disabled={busy}>Grant</button>
		</form>
		<form data-act="identity.withdraw" onsubmit={submit('identity.withdraw')}>
			<h2>Withdraw a right</h2>
			<label>Role <input name="role" required /></label>
			<label>Right <select name="right">{#each rights.rights as r (r)}<option value={r}>{r}</option>{/each}</select></label>
			<button type="submit" disabled={busy}>Withdraw</button>
		</form>
		<form data-act="units.set" onsubmit={submit('units.set')}>
			<h2>A unit's quota</h2>
			<label>Unit <input name="unit" required /></label>
			<label>Runs at once <input name="concurrent_runs" inputmode="numeric" /></label>
			<label>Monthly budget, as 250eur <input name="budget" /></label>
			<button type="submit" disabled={busy}>Set quota</button>
		</form>
		<form data-act="units.clear" onsubmit={submit('units.clear')}>
			<h2>Take a quota away</h2>
			<label>Unit <input name="unit" required /></label>
			<button type="submit" disabled={busy}>Clear</button>
		</form>
	</div>

	<h2>What each role may do</h2>
	<ul data-act="identity.rights">
		{#each rights.roles as r (r.role)}<li><strong>{r.role}</strong>: {r.rights.join(', ')}</li>{/each}
	</ul>

	<h2>Quotas per unit</h2>
	<ul data-act="units.show">
		{#each quotas as q (q.org_unit)}
			<li>{q.org_unit}: {q.concurrent_runs ?? 'any'} at once{q.budget ? `, ${Object.entries(q.budget).map(([c, a]) => `${a} ${c}`).join(', ')} a month` : ''}</li>
		{/each}
	</ul>

	<h2>Channel links</h2>
	<ul data-act="identity.links">
		{#each links as link (link.id)}
			<li>
				{link.identity} on {link.channel}{link.revoked_at ? ' · revoked' : ''}
				{#if !link.revoked_at}
					<button type="button" class="quiet" data-act="identity.revoke" disabled={busy} onclick={() => onAct('identity.revoke', { link: link.id })}>Revoke</button>
				{/if}
			</li>
		{/each}
	</ul>
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.acts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
		gap: var(--sp-250);
	}
	form {
		display: grid;
		gap: var(--sp-100);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-radius: var(--r-xl);
		padding: var(--sp-200);
		background: var(--bg-surface);
	}
	form h2 {
		margin: 0;
		font-size: var(--fs-300);
	}
	label {
		display: grid;
		gap: var(--sp-050);
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
	}
	.key code {
		word-break: break-all;
	}
	.message,
	.key {
		background: var(--status-info-surface);
		color: var(--status-info-text);
		border: var(--bw-hairline) solid var(--status-info-border);
		border-radius: var(--r-lg);
		padding: var(--sp-150) var(--sp-200);
	}
</style>
