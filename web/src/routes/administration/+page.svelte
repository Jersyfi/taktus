<!--
	A tenant's administration (UC-10.2): reads `GET /administration/links`, `/rights` and `/units`;
	each act is the surface's `/administration/...` call the inventory names (ADR-0279). The tenants
	themselves are `#/tenants`, for the instance's administration key.
-->
<script lang="ts">
	import { read, remove, send, surface, write, type Answer } from '../../lib/api';
	import AdministrationView from '../../lib/AdministrationView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';

	type Links = { links: { id: string; channel: string; identity: string; revoked_at?: string }[] };
	type Rights = { roles: { role: string; rights: string[] }[]; rights: string[] };
	type Quotas = { quotas: { org_unit: string; concurrent_runs?: number; budget?: Record<string, number> }[] };

	let signedIn = $state(true);
	let links: Links['links'] = $state([]);
	let rights: Rights = $state({ roles: [], rights: [] });
	let quotas: Quotas['quotas'] = $state([]);
	let shownKey: string | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	const base = () => surface(location.href);
	const part = (value: string | undefined) => encodeURIComponent(value ?? '');
	const list = (s: string | undefined) => (s ? s.split(',').map((x) => x.trim()).filter(Boolean) : []);

	async function load() {
		const found = await read<Links>(base(), 'administration/links');
		if (!found.ok) {
			if (found.problem.status === 401) signedIn = false;
			else message = found.problem.detail || found.problem.title;
			return;
		}
		links = found.body.links;
		const held = await read<Rights>(base(), 'administration/rights');
		if (held.ok) rights = held.body;
		const units = await read<Quotas>(base(), 'administration/units');
		if (units.ok) quotas = units.body.quotas;
	}

	$effect(() => {
		if (!signedIn) return;
		void load();
	});

	function call(act: string, v: Record<string, string>): Promise<Answer<Record<string, unknown>>> {
		const who = part(v.identity ?? '');
		switch (act) {
			case 'identity.add':
				return send(base(), 'administration/identities', { identity: v.identity, org_path: list(v.org_path), roles: list(v.roles) });
			case 'identity.key':
				return send(base(), `administration/identities/${who}/key`, {});
			case 'identity.agent-key':
				return send(base(), `administration/identities/${who}/agent-key`, {});
			case 'identity.roles':
				return write(base(), `administration/identities/${who}/roles`, 'PUT', { roles: list(v.roles) });
			case 'identity.grant':
				return write(base(), `administration/rights/${part(v.role)}/${part(v.right)}`, 'PUT', {});
			case 'identity.withdraw':
				return remove(base(), `administration/rights/${part(v.role)}/${part(v.right)}`);
			case 'identity.revoke':
				return remove(base(), `administration/links/${part(v.link)}`);
			case 'units.set':
				return write(base(), `administration/units/${part(v.unit)}`, 'PUT', {
					...(v.concurrent_runs ? { concurrent_runs: Number(v.concurrent_runs) } : {}),
					budget: list(v.budget)
				});
			default:
				return remove(base(), `administration/units/${part(v.unit)}`);
		}
	}

	async function act(name: string, values: Record<string, string>) {
		busy = true;
		shownKey = null;
		const done = await call(name, values);
		busy = false;
		if (!done.ok) {
			message = done.problem.detail || done.problem.title;
			return;
		}
		const key = done.body.key ?? done.body.agent_key;
		shownKey = typeof key === 'string' ? key : null;
		message = 'Done, and recorded.';
		await load();
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else}
	<AdministrationView {links} {rights} {quotas} {shownKey} {busy} {message} onAct={(a, v) => void act(a, v)} />
{/if}
