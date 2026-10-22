<!--
	The alerts: `GET /alerts`, read once on opening (ADR-0121, ADR-0106). The owner and the people
	the owner named read them; anyone else is told so.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import AlertsView from '../../lib/AlertsView.svelte';
	import KeyForm from '../../lib/KeyForm.svelte';
	import { currentKey } from '../../lib/key';
	import type { AlertRecord } from '../../lib/operation';

	let key = $state(currentKey());
	let refused = $state(false);
	let found: AlertRecord[] | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!key) return;
		void read<{ alerts: AlertRecord[] }>(surface(location.href), 'alerts', key).then((answer) => {
			if (answer.ok) found = answer.body.alerts;
			else if (answer.problem.status === 401) {
				refused = true;
				key = null;
			} else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !key}
	<KeyForm {refused} onKey={(k) => (key = k)} />
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
