<!--
	The needs among the reports to the owner: `GET /owner/reports` (ADR-0045, ADR-0122), read on
	opening, for the owner and whom the owner named.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import { needsOf, type OwnerReport } from '../../lib/governance';
	import SignInForm from '../../lib/SignInForm.svelte';
	import NeedsView from '../../lib/NeedsView.svelte';

	let signedIn = $state(true);
	let needs: OwnerReport[] | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<{ reports: OwnerReport[] }>(surface(location.href), 'owner/reports').then((found) => {
			if (found.ok) needs = needsOf(found.body.reports);
			else if (found.problem.status === 401) {
				signedIn = false;
			} else problem = found.problem.detail || found.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
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
