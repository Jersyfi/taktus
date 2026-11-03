<!--
	The run level of one run, live (UC-6.10, ADR-0063). It follows the run's stream of changes
	and reads the level again whenever one arrives; the stream's first event, its snapshot,
	triggers the first read, so that no change falls between reading and following (ADR-0055 §6).
	A running worker step can be taken over here, and its result handed back (UC-4.19, ADR-0128):
	the page sends the ask and the result, reads the state of every held take-over, and shows
	what the level says of each. A running worker step can be sent a message (ADR-0156). Below it, the trace inside each worker step: what its worker
	reported, live, and shared with a role (UC-6.14, ADR-0135). Both routes of a run draw this
	page: `#/runs/<run>` and `#/runs/<run>/steps/<step>`, the link a share hands on.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { surface } from './api';
	import SignInForm from './SignInForm.svelte';
	import { followLevel } from './live';
	import { motion } from './motion.svelte';
	import RunView from './RunView.svelte';
	import SteeringPanel from './SteeringPanel.svelte';
	import { messageSaid, sendMessage } from './steering';
	import TakeoverPanel from './TakeoverPanel.svelte';
	import TracePanel from './TracePanel.svelte';
	import { askTakeover, handBack, handBackRefused, readState, type Asked } from './takeover';
	import type { RunLevel, TakeoverState } from './types';

	let signedIn = $state(true);
	let absent = $state(false);
	let connected = $state(false);
	let level: RunLevel | null = $state(null);
	let asked: Asked | null = $state(null);
	let states: Record<string, TakeoverState> = $state({});
	let message: string | null = $state(null);
	let busy = $state(false);
	let steered: string | null = $state(null);
	let now = $state(new Date());
	let stop: AbortController | null = null;

	let {
		runId,
		named
	}: {
		runId: string;
		/** The step whose trace the address names: `#/runs/<run>/steps/<step>` (ADR-0135). */
		named?: string;
	} = $props();
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

	async function steer(step: string, text: string) {
		busy = true;
		const answer = await sendMessage(base(), runId, step, text);
		busy = false;
		if (!answer.ok && answer.problem.status === 401) signedIn = false;
		else steered = messageSaid(answer.ok, step, answer.ok ? '' : answer.problem.detail || answer.problem.title);
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
			<SteeringPanel level={shown} said={steered} {busy} onSend={steer} />
			<TracePanel level={shown} base={base()} {named} motionAllowed={motion.allowed} onRefused={() => (signedIn = false)} />
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
