<!--
	The incidents: `GET /incidents`, read once on opening (ADR-0121, ADR-0107).
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import IncidentsView from '../../lib/IncidentsView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { IncidentRecord } from '../../lib/operation';

	let signedIn = $state(true);
	let found: IncidentRecord[] | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<{ incidents: IncidentRecord[] }>(surface(location.href), 'incidents').then((answer) => {
			if (answer.ok) found = answer.body.incidents;
			else if (answer.problem.status === 401) {
				signedIn = false;
			} else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if found}
	<IncidentsView incidents={found} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading the incidents…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
