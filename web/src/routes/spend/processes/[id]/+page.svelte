<!--
	Where a process spent over a window, step by step (#449, ADR-0148):
	`GET /processes/{id}/spend?days=N`, read again when the reader chooses another window.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, surface } from '../../../../lib/api';
	import ProcessSpendView from '../../../../lib/ProcessSpendView.svelte';
	import SignInForm from '../../../../lib/SignInForm.svelte';
	import type { ProcessSpend } from '../../../../lib/spend';

	let signedIn = $state(true);
	let days = $state(30);
	let spend: ProcessSpend | null = $state(null);
	let problem: string | null = $state(null);

	const processId = $derived(page.params.id ?? '');

	$effect(() => {
		if (!signedIn || !processId) return;
		const path = `processes/${encodeURIComponent(processId)}/spend?days=${days}`;
		problem = null;
		void read<ProcessSpend>(surface(location.href), path).then((answer) => {
			if (answer.ok) spend = answer.body;
			else if (answer.problem.status === 401) signedIn = false;
			else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if spend}
	<ProcessSpendView {spend} {days} onDays={(n) => (days = n)} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading where the process spent…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
