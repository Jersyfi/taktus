<!--
	What a person may ask Taktus for: `GET /catalogue`, and a start of an entry as the signed-in
	reader, which opens the run (UC-1.13, ADR-0159).
-->
<script lang="ts">
	import Skeleton from '../../lib/Skeleton.svelte';
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

	async function start(process: string, inputs: Record<string, unknown>, accepted = false) {
		busy = true;
		const answer = await startEntry(base(), process, inputs, fetch, accepted);
		busy = false;
		if (!answer.ok && answer.problem.demand && !accepted) {
			// A run that needs much shows its estimated demand first; accepting starts it (ADR-0299).
			if (confirm(`${answer.problem.detail}\n\nAccept this demand and start the run?`))
				return start(process, inputs, true);
		}
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
	{#if message}<p class="status">{message}</p>{:else}<Skeleton label="Reading what you may ask for…" />{/if}
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
</style>
