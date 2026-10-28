<!--
	Where one run spent, step by step, or two runs side by side (#449, ADR-0148):
	`GET /runs/{id}/spend`, with `against` for the second run. Read once on opening: a finished
	step's figures do not change.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, surface } from '../../../../../lib/api';
	import ComparisonView from '../../../../../lib/ComparisonView.svelte';
	import SignInForm from '../../../../../lib/SignInForm.svelte';
	import SpendView from '../../../../../lib/SpendView.svelte';
	import type { RunComparison, RunSpend } from '../../../../../lib/spend';

	let signedIn = $state(true);
	let spend: RunSpend | null = $state(null);
	let compared: RunComparison | null = $state(null);
	let problem: string | null = $state(null);

	const runId = $derived(page.params.id ?? '');
	const against = $derived(page.params.against ?? '');

	$effect(() => {
		if (!signedIn || !runId) return;
		spend = null;
		compared = null;
		problem = null;
		const path = `runs/${encodeURIComponent(runId)}/spend${against ? `?against=${encodeURIComponent(against)}` : ''}`;
		void read<RunSpend | RunComparison>(surface(location.href), path).then((answer) => {
			if (answer.ok) {
				if (against) compared = answer.body as RunComparison;
				else spend = answer.body as RunSpend;
			} else if (answer.problem.status === 401) signedIn = false;
			else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if compared}
	<ComparisonView {compared} />
{:else if spend}
	<SpendView {spend} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading where the run spent…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
