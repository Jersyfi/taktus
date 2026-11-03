<!--
	The gallery a person chooses a first process from (UC-10.4, ADR-0136 §5). Reads `GET /gallery`;
	choosing sends the choices to the gallery and opens the plan dialogue on the proposal it made,
	where it is rehearsed and commissioned (UC-1.10). Sends as the signed-in reader (ADR-0119).
-->
<script lang="ts">
	import { read, send, surface } from '../../lib/api';
	import GalleryView from '../../lib/GalleryView.svelte';
	import { changeLink } from '../../lib/links';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { GalleryBlueprint, Proposal } from '../../lib/types';

	let signedIn = $state(true);
	let blueprints: GalleryBlueprint[] | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	const base = () => surface(location.href);

	$effect(() => {
		if (!signedIn) return;
		void read<{ blueprints: GalleryBlueprint[] }>(base(), 'gallery').then((found) => {
			if (found.ok) blueprints = found.body.blueprints;
			else if (found.problem.status === 401) signedIn = false;
			else message = found.problem.detail || found.problem.title;
		});
	});

	async function choose(blueprint: string, process: string, choices: Record<string, unknown>) {
		busy = true;
		const path = `gallery/${encodeURIComponent(blueprint)}/${encodeURIComponent(process)}/proposals`;
		const answer = await send<Proposal>(base(), path, { choices });
		busy = false;
		if (answer.ok) location.hash = changeLink(answer.body.process_id);
		else if (answer.problem.status === 401) signedIn = false;
		else message = answer.problem.detail || answer.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if blueprints}
	<GalleryView {blueprints} {busy} {message} onChoose={(b, p, c) => void choose(b, p, c)} />
{:else}
	<p class="status">{message ?? 'Reading the gallery…'}</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
