<!--
	Each process's level and its correction rates: `GET /autonomy` (ADR-0122), read on opening.
-->
<script lang="ts">
	import Skeleton from '../../lib/Skeleton.svelte';
	import Unavailable from '../../lib/Unavailable.svelte';
	import { read, surface } from '../../lib/api';
	import AutonomyView from '../../lib/AutonomyView.svelte';
	import type { AutonomyAnswer } from '../../lib/governance';
	import SignInForm from '../../lib/SignInForm.svelte';

	let signedIn = $state(true);
	let answer: AutonomyAnswer | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<AutonomyAnswer>(surface(location.href), 'autonomy').then((found) => {
			if (found.ok) answer = found.body;
			else if (found.problem.status === 401) {
				signedIn = false;
			} else problem = found.problem.detail || found.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if answer}
	<AutonomyView {answer} />
{:else if problem}
	<Unavailable eyebrow="Levels" {problem} />
{:else}
	<Skeleton label="Reading the levels…" />
{/if}

