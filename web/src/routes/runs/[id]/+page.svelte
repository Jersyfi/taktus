<!--
	The run level of one run, live (UC-6.10, ADR-0063). It follows the run's stream of changes
	and reads the level again whenever one arrives; the stream's first event, its snapshot,
	triggers the first read, so that no change falls between reading and following (ADR-0055 §6).
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { page } from '$app/state';
	import { surface } from '../../../lib/api';
	import SignInForm from '../../../lib/SignInForm.svelte';
	import { followLevel } from '../../../lib/live';
	import { motion } from '../../../lib/motion.svelte';
	import RunView from '../../../lib/RunView.svelte';
	import type { RunLevel } from '../../../lib/types';

	let signedIn = $state(true);
	let absent = $state(false);
	let connected = $state(false);
	let level: RunLevel | null = $state(null);
	let stop: AbortController | null = null;

	const runId = $derived(page.params.id ?? '');

	$effect(() => {
		if (!signedIn || !runId) return;
		stop?.abort();
		const controller = new AbortController();
		stop = controller;
		void followLevel<RunLevel>({
			base: surface(location.href),
			path: `levels/runs/${encodeURIComponent(runId)}`,
			scope: { run: runId },
			signal: controller.signal,
			onLevel: (found) => {
				level = found;
				absent = false;
			},
			onAbsent: () => {
				absent = true;
				level = null;
			},
			onRefused: () => {
				signedIn = false;
			},
			onConnected: (open) => (connected = open)
		});
	});
	onDestroy(() => stop?.abort());
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if absent}
	<p>No run {runId} you may see.</p>
{:else if level}
	<p class="status" aria-live="polite">{connected ? 'Live.' : 'Reconnecting…'}</p>
	<RunView {level} motionAllowed={motion.allowed} />
{:else}
	<p class="status">Reading run {runId}…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
