<!--
	The run level of one run, live (UC-6.10, ADR-0063). It follows the run's stream of changes
	and reads the level again whenever one arrives; the stream's first event, its snapshot,
	triggers the first read, so that no change falls between reading and following (ADR-0055 §6).
	A running worker step can be taken over here, and its result handed back (UC-4.19, ADR-0128):
	the page sends the ask and the result, reads the state of every held take-over, and shows
	what the level says of each.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { page } from '$app/state';
	import { surface } from '../../../lib/api';
	import SignInForm from '../../../lib/SignInForm.svelte';
	import { followLevel } from '../../../lib/live';
	import { motion } from '../../../lib/motion.svelte';
	import RunView from '../../../lib/RunView.svelte';
	import TakeoverPanel from '../../../lib/TakeoverPanel.svelte';
	import { askTakeover, handBack, handBackRefused, readState, type Asked } from '../../../lib/takeover';
	import type { RunLevel, TakeoverState } from '../../../lib/types';

	let signedIn = $state(true);
	let absent = $state(false);
	let connected = $state(false);
	let level: RunLevel | null = $state(null);
	let asked: Asked | null = $state(null);
	let states: Record<string, TakeoverState> = $state({});
	let message: string | null = $state(null);
	let busy = $state(false);
	let now = $state(new Date());
	let stop: AbortController | null = null;

	const runId = $derived(page.params.id ?? '');
	const base = () => surface(location.href);

	$effect(() => {
		if (!signedIn || !runId) return;
		stop?.abort();
		asked = null;
		const controller = new AbortController();
		stop = controller;
		void followLevel<RunLevel>({
			base: base(),
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

	// The time left on a held take-over moves without a change on the stream.
	$effect(() => {
		const timer = setInterval(() => (now = new Date()), 30_000);
		return () => clearInterval(timer);
	});

	// The state of every held take-over, read once it is served.
	$effect(() => {
		if (!level) return;
		for (const step of level.steps) {
			const t = step.takeover;
			if (t?.standing !== 'held' || states[t.id]) continue;
			void readState(base(), runId, t.id).then((answer) => {
				if (answer.ok) states = { ...states, [t.id]: answer.body };
				else if (answer.problem.status === 401) signedIn = false;
			});
		}
	});

	async function takeOver(step: string) {
		busy = true;
		const answer = await askTakeover(base(), runId, step);
		busy = false;
		if (answer.ok) {
			asked = { takeover: answer.body.takeover, step };
			message = null;
		} else if (answer.problem.status === 401) {
			signedIn = false;
		} else message = `Not taken over: ${answer.problem.detail || answer.problem.title}`;
	}

	async function giveBack(takeover: string, result: unknown) {
		busy = true;
		const answer = await handBack(base(), runId, takeover, result);
		busy = false;
		if (answer.ok) {
			message = 'Handed back. The result counts as yours, and the run continues.';
			if (asked?.takeover === takeover) asked = null;
		} else if (answer.problem.status === 401) {
			signedIn = false;
		} else message = handBackRefused(answer.problem.status, answer.problem.detail);
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if absent}
	<p>No run {runId} you may see.</p>
{:else if level}
	<p class="status" aria-live="polite">{connected ? 'Live.' : 'Reconnecting…'}</p>
	{@const shown = level}
	<RunView level={shown} motionAllowed={motion.allowed}>
		{#snippet acts()}
			<TakeoverPanel level={shown} {asked} {states} {message} {busy} {now} onTakeOver={takeOver} onHandBack={giveBack} />
		{/snippet}
	</RunView>
{:else}
	<p class="status">Reading run {runId}…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
