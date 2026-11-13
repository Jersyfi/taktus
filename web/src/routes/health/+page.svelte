<!--
	The instance's health: `GET /administration/health`, and an update prepared as a plan with
	`POST /administration/update` (ADR-0295, ADR-0296). Both need a role holding
	tenant.administer; anyone else is told so.
-->
<script lang="ts">
	import { read, send, surface } from '../../lib/api';
	import HealthView from '../../lib/HealthView.svelte';
	import type { Health } from '../../lib/operation';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Unavailable from '../../lib/Unavailable.svelte';

	type Opened = { draft: { id: string; version: number }; missing: string[] };

	let signedIn = $state(true);
	let found: Health | null = $state(null);
	let problem: string | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);

	$effect(() => {
		if (!signedIn) return;
		void read<Health>(surface(location.href), 'administration/health').then((answer) => {
			if (answer.ok) found = answer.body;
			else if (answer.problem.status === 401) signedIn = false;
			else problem = answer.problem.detail || answer.problem.title;
		});
	});

	async function prepare(to: string, said: string) {
		busy = true;
		const opened = await send<Opened>(surface(location.href), 'administration/update', { to, said });
		busy = false;
		if (!opened.ok) {
			message = opened.problem.detail || opened.problem.title;
			return;
		}
		const lacks = opened.body.missing.length ? ` It still lacks ${opened.body.missing.join(', ')}.` : '';
		message = `Plan draft ${opened.body.draft.id} opened for the update to ${to}.${lacks} Work it out and commission it under Plan.`;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if found}
	<HealthView health={found} {message} {busy} onPrepare={prepare} />
	<p><a href="#/plans">Open the plan dialogue</a></p>
{:else if problem}
	<Unavailable eyebrow="Health" {problem} />
{:else}
	<p class="status">Reading the instance's health…</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
