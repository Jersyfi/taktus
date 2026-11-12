<!--
	The processes Taktus proposes to the reader (UC-4.4): reads `GET /process-proposals`, and
	answers one with `POST /process-proposals/{proposal}/accept` or `/decline` (ADR-0270). It needs
	a person's sign-in; the list is read again after every act.
-->
<script lang="ts">
	import { read, send, surface } from '../../lib/api';
	import ProposedView from '../../lib/ProposedView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import { act, type Decided, type ProcessProposals } from '../../lib/proposed';

	let signedIn = $state(true);
	let listed: ProcessProposals | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	const base = () => surface(location.href);

	async function load() {
		const done = await read<ProcessProposals>(base(), 'process-proposals');
		if (done.ok) listed = done.body;
		else if (done.problem.status === 401) signedIn = false;
		else message = done.problem.detail || done.problem.title;
	}

	async function decide(id: string, what: 'accept' | 'decline') {
		busy = true;
		const done = await send<Decided>(base(), act(id, what), {});
		busy = false;
		if (done.ok) {
			message = done.body.run_id ? `Taktus is building it in run ${done.body.run_id}.` : 'Declined.';
			await load();
		} else if (done.problem.status === 401) signedIn = false;
		else message = done.problem.detail || done.problem.title;
	}

	$effect(() => {
		if (!signedIn) return;
		void load();
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if listed}
	<ProposedView
		{listed}
		{busy}
		{message}
		onAccept={(id) => void decide(id, 'accept')}
		onDecline={(id) => void decide(id, 'decline')}
	/>
{:else}
	<p class="status">{message ?? 'Reading what Taktus proposes…'}</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
