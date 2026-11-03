<!--
	What a person may ask Taktus for: `GET /catalogue`, and a start of an entry as the signed-in
	reader, which opens the run (UC-1.13, ADR-0159).
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import CatalogueView from '../../lib/CatalogueView.svelte';
	import { runLink } from '../../lib/links';
	import SignInForm from '../../lib/SignInForm.svelte';
	import { CATALOGUE, startEntry, type Catalogue } from '../../lib/views';

	let signedIn = $state(true);
	let catalogue: Catalogue | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	const base = () => surface(location.href);

	$effect(() => {
		if (!signedIn) return;
		void read<Catalogue>(base(), CATALOGUE).then((found) => {
			if (found.ok) catalogue = found.body;
			else if (found.problem.status === 401) signedIn = false;
			else message = found.problem.detail || found.problem.title;
		});
	});

	async function start(process: string, inputs: Record<string, unknown>) {
		busy = true;
		const answer = await startEntry(base(), process, inputs);
		busy = false;
		if (answer.ok) location.hash = runLink(answer.body.run_id);
		else if (answer.problem.status === 401) signedIn = false;
		else message = answer.problem.detail || answer.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if catalogue}
	<CatalogueView {catalogue} {busy} {message} onStart={(p, i) => void start(p, i)} />
{:else}
	<p class="status">{message ?? 'Reading what you may ask for…'}</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
