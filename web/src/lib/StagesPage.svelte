<!--
	The stages of one run, live (UC-6.15). Drawn from `GET /levels/runs/<run>/stages`, which is
	computed from the run level's records; the page stores nothing. It follows the run's stream of
	changes and reads the stages again whenever one arrives, so a change reaches the view without
	a reload (ADR-0055). Every stage is written out: its name, its state and, where it waits, the
	role. The link leads to the run level, for a reader who may see it.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { surface } from './api';
	import { followLevel } from './live';
	import { runLink } from './links';
	import SignInForm from './SignInForm.svelte';
	import type { StageView } from './types';

	let signedIn = $state(true);
	let absent = $state(false);
	let connected = $state(false);
	let view: StageView | null = $state(null);
	let stop: AbortController | null = null;

	let { runId }: { runId: string } = $props();

	$effect(() => {
		if (!signedIn || !runId) return;
		stop?.abort();
		const controller = new AbortController();
		stop = controller;
		void followLevel<StageView>({
			base: surface(location.href),
			path: `levels/runs/${encodeURIComponent(runId)}/stages`,
			scope: { run: runId },
			signal: controller.signal,
			onLevel: (found) => {
				view = found;
				absent = false;
			},
			onAbsent: () => {
				absent = true;
				view = null;
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
{:else if view}
	<p class="status" aria-live="polite">{connected ? 'Live.' : 'Reconnecting…'}</p>
	<section aria-labelledby="stages-title">
		<h1 id="stages-title">{view.summary}</h1>
		<ol class="stages">
			{#each view.stages as stage (stage.name)}
				<li class={stage.state} aria-current={stage.state === 'current' ? 'step' : undefined}>
					<span class="name">{stage.name}</span>
					<span class="state">{stage.state}</span>
					{#if stage.waiting_for}<span class="role">waiting for the role {stage.waiting_for}</span>{/if}
					<span class="visually-hidden">{stage.text}</span>
				</li>
			{/each}
		</ol>
		<p><a href={runLink(view.run_id)}>The run level</a></p>
	</section>
{:else}
	<p class="status">Reading the stages of run {runId}…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
	.stages {
		list-style: none;
		padding: 0;
	}
	li {
		display: flex;
		gap: 0.75rem;
		padding: 0.4rem 0;
	}
	li.ahead {
		color: var(--muted);
	}
	li.current .name {
		font-weight: 600;
	}
	.state {
		text-transform: uppercase;
		font-size: 0.8rem;
	}
	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
	}
</style>
