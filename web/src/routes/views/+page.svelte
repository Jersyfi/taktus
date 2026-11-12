<!--
	The reader's views and their figures (UC-6.4, ADR-0241): `GET /views`, read once on opening.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import type { Views } from '../../lib/figures';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Unavailable from '../../lib/Unavailable.svelte';
	import ViewsView from '../../lib/ViewsView.svelte';

	let signedIn = $state(true);
	let views: Views | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<Views>(surface(location.href), 'views').then((answer) => {
			if (answer.ok) views = answer.body;
			else if (answer.problem.status === 401) signedIn = false;
			else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if views}
	<ViewsView {views} />
{:else if problem}
	<Unavailable eyebrow="Figures" {problem} />
{:else}
	<p class="status">Reading your views…</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
