<!--
	A tenant's introduction in stages (ADR-0137, ADR-0191): `GET /stages`, read on opening; a stage
	is opened with `POST /stages/{id}/open`, and the page reads the stages again. The surface
	admits the plan's responsible role and says so to anyone else.
-->
<script lang="ts">
	import Unavailable from '../../lib/Unavailable.svelte';
	import { read, send, surface } from '../../lib/api';
	import IntroductionView from '../../lib/IntroductionView.svelte';
	import type { Introduction, StageDocument } from '../../lib/introduction';
	import SignInForm from '../../lib/SignInForm.svelte';

	let signedIn = $state(true);
	let intro: Introduction | null = $state(null);
	let problem: string | null = $state(null);
	let opening: string | null = $state(null);

	async function load() {
		const answer = await read<Introduction>(surface(location.href), 'stages');
		if (answer.ok) intro = answer.body;
		else if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
	}

	$effect(() => {
		if (signedIn) void load();
	});

	async function open(stage: StageDocument) {
		problem = null;
		opening = stage.stage.id;
		const answer = await send<StageDocument>(surface(location.href), `stages/${encodeURIComponent(stage.stage.id)}/open`, {});
		opening = null;
		if (answer.ok) await load();
		else if (answer.problem.status === 401) signedIn = false;
		else problem = answer.problem.detail || answer.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if intro}
	<IntroductionView {intro} {problem} {opening} onOpen={open} />
{:else if problem}
	<Unavailable eyebrow="Introduction" {problem} />
{:else}
	<p class="status">Reading the introduction…</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
