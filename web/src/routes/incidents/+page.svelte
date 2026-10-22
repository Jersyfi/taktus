<!--
	The incidents: `GET /incidents`, read once on opening (ADR-0121, ADR-0107).
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import IncidentsView from '../../lib/IncidentsView.svelte';
	import KeyForm from '../../lib/KeyForm.svelte';
	import { currentKey } from '../../lib/key';
	import type { IncidentRecord } from '../../lib/operation';

	let key = $state(currentKey());
	let refused = $state(false);
	let found: IncidentRecord[] | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!key) return;
		void read<{ incidents: IncidentRecord[] }>(surface(location.href), 'incidents', key).then((answer) => {
			if (answer.ok) found = answer.body.incidents;
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
