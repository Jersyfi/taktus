<!--
	The backup: `GET /backup`, read once on opening (ADR-0121, ADR-0106). The owner and the people
	the owner named read it; anyone else is told so.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import BackupView from '../../lib/BackupView.svelte';
	import KeyForm from '../../lib/KeyForm.svelte';
	import { currentKey } from '../../lib/key';
	import type { BackupRecord } from '../../lib/operation';

	let key = $state(currentKey());
	let refused = $state(false);
	let found: BackupRecord | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!key) return;
		void read<BackupRecord>(surface(location.href), 'backup', key).then((answer) => {
			if (answer.ok) found = answer.body;
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
	<BackupView backup={found} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading the backup…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
