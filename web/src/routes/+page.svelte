<!--
	The runs the reader may see, as the tenant's stream says they stand, each leading to its run
	level. Not the overview of UC-6.10 (#191): a way in, until the overview exists.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { surface } from '../lib/api';
	import KeyForm from '../lib/KeyForm.svelte';
	import { currentKey } from '../lib/key';
	import { applyToRuns, type Runs } from '../lib/live';
	import { processLink } from '../lib/links';
	import { follow } from '../lib/stream';

	let key = $state(currentKey());
	let refused = $state(false);
	let connected = $state(false);
	let runs: Runs = $state(new Map());
	let stop: AbortController | null = null;

	function start(chosen: string) {
		stop?.abort();
		const controller = new AbortController();
		stop = controller;
		refused = false;
		void follow({
			url: new URL('changes', surface(location.href)),
			key: chosen,
			signal: controller.signal,
			onConnected: (open) => (connected = open),
			onEvent: (event) => (runs = applyToRuns(runs, event))
		}).then((ended) => {
			if (ended.reason === 'refused') {
				refused = true;
				key = null;
			}
		});
	}

	$effect(() => {
		if (key) start(key);
	});
	onDestroy(() => stop?.abort());

	const listed = $derived([...runs.values()].reverse());
</script>

{#if !key}
	<KeyForm {refused} onKey={(k) => (key = k)} />
{:else}
	<h1>Runs</h1>
	<p class="status" aria-live="polite">{connected ? 'Live.' : 'Connecting…'}</p>
	{#if listed.length === 0}
		<p>No run you may see.</p>
	{:else}
		<ul>
			{#each listed as run (run.id)}
				<li>
					<a href="#/runs/{encodeURIComponent(run.id)}">{run.id}</a>
					{#if run.process_version}<a href={processLink(run.process_version)}>{run.process_version}</a>{/if}
					<span class="state">{run.state.replace('_', ' ')}</span>
				</li>
			{/each}
		</ul>
	{/if}
{/if}

<style>
	ul {
		list-style: none;
		padding: 0;
	}
	li {
		display: flex;
		gap: 1rem;
		padding: 0.4rem 0;
		border-bottom: 1px solid var(--line);
		flex-wrap: wrap;
	}
	a {
		color: inherit;
		font-weight: 600;
	}
	.state,
	.status {
		color: var(--muted);
	}
</style>
