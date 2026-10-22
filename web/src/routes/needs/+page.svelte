<!--
	The needs among the reports to the owner: `GET /owner/reports` (ADR-0045, ADR-0122), read on
	opening, for the owner and whom the owner named.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import { needsOf, type OwnerReport } from '../../lib/governance';
	import KeyForm from '../../lib/KeyForm.svelte';
	import { currentKey } from '../../lib/key';
	import NeedsView from '../../lib/NeedsView.svelte';

	let key = $state(currentKey());
	let refused = $state(false);
	let needs: OwnerReport[] | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!key) return;
		void read<{ reports: OwnerReport[] }>(surface(location.href), 'owner/reports', key).then((found) => {
			if (found.ok) needs = needsOf(found.body.reports);
			else if (found.problem.status === 401) {
				refused = true;
				key = null;
			} else problem = found.problem.detail || found.problem.title;
		});
	});
</script>

{#if !key}
	<KeyForm {refused} onKey={(k) => (key = k)} />
{:else if needs}
	<NeedsView {needs} />
{:else if problem}
	<p role="alert">{problem}</p>
{:else}
	<p class="status">Reading the needs…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
