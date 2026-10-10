<!--
	The process level of one process version, live (UC-6.10, ADR-0064). It follows the process's
	stream of changes and reads the level again whenever one arrives, as the run level does
	(ADR-0063). Without a version in the address, the active version is drawn.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { page } from '$app/state';
	import { surface } from '../../../../lib/api';
	import KeyForm from '../../../../lib/KeyForm.svelte';
	import { currentKey } from '../../../../lib/key';
	import { followLevel } from '../../../../lib/live';
	import { motion } from '../../../../lib/motion.svelte';
	import ProcessView from '../../../../lib/ProcessView.svelte';
	import type { ProcessLevel } from '../../../../lib/types';

	let key = $state(currentKey());
	let refused = $state(false);
	let absent = $state(false);
	let connected = $state(false);
	let level: ProcessLevel | null = $state(null);
	let stop: AbortController | null = null;

	const processId = $derived(page.params.id ?? '');
	const version = $derived(page.params.version ?? '');

	$effect(() => {
		if (!key || !processId) return;
		stop?.abort();
		const controller = new AbortController();
		stop = controller;
		refused = false;
		level = null;
		const path = `levels/processes/${encodeURIComponent(processId)}${
			version ? `?version=${encodeURIComponent(version)}` : ''
		}`;
		void followLevel<ProcessLevel>({
			base: surface(location.href),
			path,
			scope: { process: processId },
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
	<p>No process {processId}{version ? `@${version}` : ''} you may see.</p>
{:else if level}
	<p class="status" aria-live="polite">{connected ? 'Live.' : 'Reconnecting…'}</p>
	<ProcessView {level} motionAllowed={motion.allowed} />
{:else}
	<p class="status">Reading process {processId}…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
