<!--
	The reader's automation coach (UC-13.3): reads `GET /coach`, sets it with `PUT /coach`, and
	answers a hint with `POST /coach/hints/{hint}/dismiss` or `/accept` (ADR-0279).
-->
<script lang="ts">
	import { read, send, surface, write, type Answer } from '../../lib/api';
	import CoachView from '../../lib/CoachView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { CoachState } from '../../lib/workspace';

	let signedIn = $state(true);
	let coach: CoachState | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	const base = () => surface(location.href);

	async function took(answer: Promise<Answer<CoachState>>) {
		busy = true;
		const done = await answer;
		busy = false;
		if (done.ok) coach = done.body;
		else if (done.problem.status === 401) signedIn = false;
		else message = done.problem.detail || done.problem.title;
	}

	$effect(() => {
		if (!signedIn) return;
		void took(read<CoachState>(base(), 'coach'));
	});

	const hint = (id: string) => `coach/hints/${encodeURIComponent(id)}`;
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if coach}
	<CoachView
		{coach}
		{busy}
		{message}
		onSet={(on, perWeek) => void took(write<CoachState>(base(), 'coach', 'PUT', { on, hints_per_week: perWeek }))}
		onDismiss={(id) => void took(send<CoachState>(base(), `${hint(id)}/dismiss`, {}))}
		onAccept={(id, version) => void took(send<CoachState>(base(), `${hint(id)}/accept`, { process_version: version }))}
	/>
{:else}
	<p class="status">{message ?? 'Reading your coach…'}</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
