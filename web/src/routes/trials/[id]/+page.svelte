<!--
	One model trial with its report (#448, ADR-0149): `GET /trials/{id}`, read again every few
	seconds while its runs have not settled, and once after.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, surface } from '../../../lib/api';
	import SignInForm from '../../../lib/SignInForm.svelte';
	import TrialView from '../../../lib/TrialView.svelte';
	import type { TrialRead } from '../../../lib/spend';

	const AGAIN_MS = 5000;

	let signedIn = $state(true);
	let found: TrialRead | null = $state(null);
	let problem: string | null = $state(null);

	const trialId = $derived(page.params.id ?? '');

	$effect(() => {
		if (!signedIn || !trialId) return;
		let timer: ReturnType<typeof setTimeout> | undefined;
		let stopped = false;
		const once = (): Promise<void> =>
			read<TrialRead>(surface(location.href), `trials/${encodeURIComponent(trialId)}`).then((answer) => {
				if (stopped) return;
				if (answer.ok) {
					found = answer.body;
					if (!answer.body.settled) timer = setTimeout(() => void once(), AGAIN_MS);
				} else if (answer.problem.status === 401) signedIn = false;
				else problem = answer.problem.detail || answer.problem.title;
			});
		void once();
		return () => {
			stopped = true;
			clearTimeout(timer);
		};
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if found}
	<TrialView read={found} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading the trial…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
