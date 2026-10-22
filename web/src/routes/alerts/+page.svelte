<!--
	The alerts: `GET /alerts`, read once on opening (ADR-0121, ADR-0106). The owner and the people
	the owner named read them; anyone else is told so.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import AlertsView from '../../lib/AlertsView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { AlertRecord } from '../../lib/operation';

	let signedIn = $state(true);
	let found: AlertRecord[] | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<{ alerts: AlertRecord[] }>(surface(location.href), 'alerts').then((answer) => {
			if (answer.ok) found = answer.body.alerts;
			else if (answer.problem.status === 401) {
				signedIn = false;
			} else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if found}
	<AlertsView alerts={found} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading the alerts…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
