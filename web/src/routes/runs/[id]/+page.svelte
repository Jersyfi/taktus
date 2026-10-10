<!--
	The run level of one run, live (UC-6.10, ADR-0063). It follows the run's stream of changes
	and reads the level again whenever one arrives; the stream's first event, its snapshot,
	triggers the first read, so that no change falls between reading and following (ADR-0055 §6).
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { page } from '$app/state';
	import { surface } from '../../../lib/api';
	import KeyForm from '../../../lib/KeyForm.svelte';
	import { currentKey } from '../../../lib/key';
	import { followLevel } from '../../../lib/live';
	import { motion } from '../../../lib/motion.svelte';
	import RunView from '../../../lib/RunView.svelte';
	import type { RunLevel } from '../../../lib/types';

	let key = $state(currentKey());
	let refused = $state(false);
	let absent = $state(false);
	let connected = $state(false);
	let level: RunLevel | null = $state(null);
	let stop: AbortController | null = null;

	const runId = $derived(page.params.id ?? '');

	$effect(() => {
		if (!key || !runId) return;
		stop?.abort();
		const controller = new AbortController();
		stop = controller;
		refused = false;
		void followLevel<RunLevel>({
			base: surface(location.href),
			path: `levels/runs/${encodeURIComponent(runId)}`,
			scope: { run: runId },
			key,
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
				refused = true;
				key = null;
			},
			onConnected: (open) => (connected = open)
		});
	});
	onDestroy(() => stop?.abort());
</script>

{#if !key}
	<KeyForm {refused} onKey={(k) => (key = k)} />
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
