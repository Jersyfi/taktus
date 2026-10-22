<!--
	The origin of one step's result (UC-6.10, ADR-0068). A recorded result does not change: the
	page reads it once, and draws it as it was recorded.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, surface } from '../../../../lib/api';
	import SignInForm from '../../../../lib/SignInForm.svelte';
	import { motion } from '../../../../lib/motion.svelte';
	import OriginView from '../../../../lib/OriginView.svelte';
	import type { OriginLevel } from '../../../../lib/types';

	let signedIn = $state(true);
	let absent = $state(false);
	let level: OriginLevel | null = $state(null);

	const runId = $derived(page.params.run ?? '');
	const stepId = $derived(page.params.step ?? '');

	$effect(() => {
		if (!signedIn || !runId || !stepId) return;
		const path = `levels/origins/${encodeURIComponent(runId)}/${encodeURIComponent(stepId)}`;
		level = null;
		absent = false;
		void read<OriginLevel>(surface(location.href), path).then((answer) => {
			if (answer.ok) level = answer.body;
			else if (answer.problem.status === 401) {
				signedIn = false;
			} else absent = true;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if absent}
	<p>No result of {runId}/{stepId} you may see.</p>
{:else if level}
	<OriginView {level} motionAllowed={motion.allowed} />
{:else}
	<p class="status">Reading where the result came from…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
