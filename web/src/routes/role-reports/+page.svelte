<!--
	The reports for a role (UC-6.2, ADR-0242): `GET /reports/definitions` on opening, and a report
	composed now with `GET /reports/definitions/{id}/now` when its button is pressed. The owner's
	own reports live under `#/reports/<id>`, a page of their own.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import type { ComposedReport, Definitions } from '../../lib/figures';
	import RoleReportsView from '../../lib/RoleReportsView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Unavailable from '../../lib/Unavailable.svelte';

	let signedIn = $state(true);
	let definitions: Definitions | null = $state(null);
	let problem: string | null = $state(null);
	let composed = $state<Record<string, ComposedReport>>({});
	let problems = $state<Record<string, string>>({});
	let busy: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<Definitions>(surface(location.href), 'reports/definitions').then((answer) => {
			if (answer.ok) definitions = answer.body;
			else if (answer.problem.status === 401) signedIn = false;
			else problem = answer.problem.detail || answer.problem.title;
		});
	});

	async function compose(id: string) {
		busy = id;
		const answer = await read<ComposedReport>(surface(location.href), `reports/definitions/${encodeURIComponent(id)}/now`);
		busy = null;
		if (answer.ok) {
			composed = { ...composed, [id]: answer.body };
			problems = Object.fromEntries(Object.entries(problems).filter(([k]) => k !== id));
		} else if (answer.problem.status === 401) signedIn = false;
		else problems = { ...problems, [id]: answer.problem.detail || answer.problem.title };
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if definitions}
	<RoleReportsView {definitions} {composed} {problems} {busy} onCompose={compose} />
{:else if problem}
	<Unavailable eyebrow="Reports" {problem} />
{:else}
	<p class="status">Reading the reports for your roles…</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
