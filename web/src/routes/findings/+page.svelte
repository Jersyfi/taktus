<!--
	This instance's findings and their review: `GET /findings`, an answer read back by
	`POST /findings/{lack}/review`, and the reading confirmed by `…/review/confirm` (ADR-0122).
	The page shows what the surface sends back and decides nothing itself.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import FindingsView from '../../lib/FindingsView.svelte';
	import {
		confirmReading,
		readBack,
		type FindingsAnswer,
		type ReviewChoice,
		type ReviewReading
	} from '../../lib/governance';
	import SignInForm from '../../lib/SignInForm.svelte';

	let signedIn = $state(true);
	let answer: FindingsAnswer | null = $state(null);
	let reading: ReviewReading | null = $state(null);
	let message: string | null = $state(null);
	let problem: string | null = $state(null);
	let busy = $state(false);

	function refuse(status: number): boolean {
		if (status !== 401) return false;
		signedIn = false;
		return true;
	}

	async function load() {
		if (!signedIn) return;
		const found = await read<FindingsAnswer>(surface(location.href), 'findings');
		if (found.ok) answer = found.body;
		else if (!refuse(found.problem.status)) problem = found.problem.detail || found.problem.title;
	}

	$effect(() => {
		if (signedIn) void load();
	});

	async function onAnswer(lack: string, choice: ReviewChoice) {
		if (!signedIn) return;
		busy = true;
		const back = await readBack(surface(location.href), lack, choice);
		busy = false;
		if (back.ok) {
			reading = back.body;
			message = null;
		} else if (!refuse(back.problem.status)) message = back.problem.detail || back.problem.title;
	}

	async function onConfirm(confirmed: boolean) {
		if (!signedIn || !reading) return;
		busy = true;
		const done = await confirmReading(surface(location.href), reading, confirmed);
		busy = false;
		reading = null;
		if (done.ok) message = done.body.message;
		else if (!refuse(done.problem.status)) message = done.problem.detail || done.problem.title;
		await load();
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if answer}
	<FindingsView {answer} {reading} {message} {busy} {onAnswer} {onConfirm} />
{:else if problem}
	<p role="alert">{problem}</p>
{:else}
	<p class="status">Reading the findings…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
