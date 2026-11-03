<!--
	The model trials and those offered (#448, ADR-0149): `GET /trials`; a trial is started with
	`POST /trials`, and the page then opens it.
-->
<script lang="ts">
	import { read, send, surface } from '../../lib/api';
	import SignInForm from '../../lib/SignInForm.svelte';
	import TrialsView from '../../lib/TrialsView.svelte';
	import { trialsLink, type Trial, type Trials } from '../../lib/spend';

	let signedIn = $state(true);
	let trials: Trials | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<Trials>(surface(location.href), 'trials').then((answer) => {
			if (answer.ok) trials = answer.body;
			else if (answer.problem.status === 401) signedIn = false;
			else problem = answer.problem.detail || answer.problem.title;
		});
	});

	async function start(purpose: string, candidates: string[], occasion: string) {
		problem = null;
		const answer = await send<Trial>(surface(location.href), 'trials', { purpose, candidates, occasion });
		if (answer.ok) location.hash = trialsLink(answer.body.id);
		else if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if trials}
	<TrialsView {trials} {problem} onStart={start} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading the model trials…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
