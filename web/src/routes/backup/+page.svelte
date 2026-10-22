<!--
	The backup: `GET /backup`, read once on opening (ADR-0121, ADR-0106). The owner and the people
	the owner named read it; anyone else is told so.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import BackupView from '../../lib/BackupView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { BackupRecord } from '../../lib/operation';

	let signedIn = $state(true);
	let found: BackupRecord | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<BackupRecord>(surface(location.href), 'backup').then((answer) => {
			if (answer.ok) found = answer.body;
			else if (answer.problem.status === 401) {
				signedIn = false;
			} else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
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
