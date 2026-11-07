<!--
	The reader's own page: `GET /decisions/response-times`, which the surface computes for its
	reader alone (ADR-0015), and what Taktus took off them, `GET /me/relief` (UC-13.5, ADR-0245
	§1), whose settings the reader sets with `PUT /me/relief/settings`. Read once on opening, and
	the relief again after a save.
-->
<script lang="ts">
	import { put, read, surface } from '../../lib/api';
	import ReliefSection from '../../lib/ReliefSection.svelte';
	import type { OwnRelief, ReliefSettings } from '../../lib/relief';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { ResponseTimes } from '../../lib/types';
	import YoursView from '../../lib/YoursView.svelte';

	let signedIn = $state(true);
	let times: ResponseTimes | null = $state(null);
	let relief: OwnRelief | null = $state(null);
	let reliefProblem: string | null = $state(null);
	let said: string | null = $state(null);
	let busy = $state(false);

	async function loadRelief() {
		const answer = await read<OwnRelief>(surface(location.href), 'me/relief');
		if (answer.ok) relief = answer.body;
		else if (answer.problem.status === 401) signedIn = false;
		else reliefProblem = answer.problem.detail || answer.problem.title;
	}

	$effect(() => {
		if (!signedIn) return;
		void read<ResponseTimes>(surface(location.href), 'decisions/response-times').then((answer) => {
			if (answer.ok) times = answer.body;
			else if (answer.problem.status === 401) {
				signedIn = false;
			}
		});
		void loadRelief();
	});

	async function save(settings: ReliefSettings) {
		busy = true;
		said = null;
		reliefProblem = null;
		const answer = await put<unknown>(surface(location.href), 'me/relief/settings', settings);
		busy = false;
		if (answer.ok) {
			said = 'Saved.';
			await loadRelief();
		} else if (answer.problem.status === 401) signedIn = false;
		else reliefProblem = answer.problem.detail || answer.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if times}
	<YoursView {times} />
{:else}
	<p class="status">Reading your own times…</p>
{/if}

{#if signedIn}
	{#if relief}
		<ReliefSection {relief} problem={reliefProblem} {said} {busy} onSave={save} />
	{:else if reliefProblem}
		<p class="status" role="alert">{reliefProblem}</p>
	{/if}
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
