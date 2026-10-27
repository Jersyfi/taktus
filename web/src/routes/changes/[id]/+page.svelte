<!--
	A process changed in dialogue, and rolled back (UC-4.15, ADR-0091 §6). Reads the process level
	for its versions and the process's proposals; sends only the writes ADR-0091 §6 names, as the
	signed-in reader (ADR-0119).
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, send, surface } from '../../../lib/api';
	import ChangeView from '../../../lib/ChangeView.svelte';
	import SignInForm from '../../../lib/SignInForm.svelte';
	import type { Evaluated, ProcessLevel, Proposal, RunLevel } from '../../../lib/types';

	let signedIn = $state(true);
	let absent = $state(false);
	let level: ProcessLevel | null = $state(null);
	let proposals: Proposal[] = $state([]);
	let rehearsals: Record<string, RunLevel> = $state({});
	let evaluations: Record<string, Evaluated> = $state({});
	let message: string | null = $state(null);
	let busy = $state(false);

	const processId = $derived(page.params.id ?? '');
	const base = () => surface(location.href);
	const path = (rest: string) => `processes/${encodeURIComponent(processId)}${rest}`;

	async function reload() {
		if (!signedIn) return;
		const [found, listed] = await Promise.all([
			read<ProcessLevel>(base(), `levels/${path('')}`),
			read<{ proposals: Proposal[] }>(base(), path('/proposals'))
		]);
		if (!found.ok) {
			if (found.problem.status === 401) {
				signedIn = false;
			} else absent = true;
			return;
		}
		level = found.body;
		proposals = listed.ok ? listed.body.proposals : [];
		const seen: Record<string, RunLevel> = {};
		await Promise.all(
			proposals
				.filter((p) => p.rehearsal_run && (p.state === 'proposed' || p.state === 'rehearsed'))
				.map(async (p) => {
					const run = await read<RunLevel>(base(), `levels/runs/${encodeURIComponent(p.rehearsal_run!)}`);
					if (run.ok) seen[p.id] = run.body;
				})
		);
		rehearsals = seen;
		// A proposal held to the process's cases is read on its own, which carries the comparison
		// (ADR-0134 §9): an open one, and a commissioned one that may carry an override's reason.
		const held: Record<string, Evaluated> = {};
		await Promise.all(
			proposals
				.filter((p) => p.evaluation && p.state !== 'discarded')
				.map(async (p) => {
					const one = await read<Proposal>(base(), path(`/proposals/${encodeURIComponent(p.id)}`));
					if (one.ok && one.body.evaluated) held[p.id] = one.body.evaluated;
				})
		);
		evaluations = held;
	}

	$effect(() => {
		if (signedIn && processId) void reload();
	});

	// A rehearsal under way is read again until it ends, so the result appears without a reload.
	const ended = ['finished', 'failed', 'escalated', 'halted', 'cancelled', 'stopped'];
	$effect(() => {
		// So is an evaluation on the cases until it is scored.
		const under =
			Object.values(rehearsals).some((r) => !ended.includes(r.run.state)) ||
			Object.values(evaluations).some((e) => e.state !== 'scored');
		if (!signedIn || !under) return;
		const timer = setInterval(() => void reload(), 3000);
		return () => clearInterval(timer);
	});

	async function act(rest: string, body: unknown, done: (answer: Record<string, unknown>) => string) {
		if (!signedIn) return;
		busy = true;
		const answer = await send<Record<string, unknown>>(base(), path(rest), body);
		busy = false;
		if (answer.ok) message = done(answer.body);
		else if (answer.problem.status === 401) {
			signedIn = false;
		} else message = answer.problem.detail || answer.problem.title;
		await reload();
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if absent}
	<p>No process {processId} you may see.</p>
{:else if level}
	<ChangeView
		{level}
		{proposals}
		{rehearsals}
		{evaluations}
		{busy}
		{message}
		onAsk={(request) =>
			act('/proposals', { request }, (a) => `S-07 is working out your change in run ${a['run']}. The proposal appears here.`)}
		onRehearse={(id) =>
			act(`/proposals/${encodeURIComponent(id)}/rehearse`, {}, (a) => `Rehearsing in run ${a['run']}; nothing leaves the system.`)}
		onCommission={(id, override) =>
			act(`/proposals/${encodeURIComponent(id)}/commission`, override ? { override } : {}, (a) =>
				override
					? `Version ${a['version']} is registered and active, against the verdict; your reason is recorded.`
					: `Version ${a['version']} is registered and active.`
			)}
		onDiscard={(id) => act(`/proposals/${encodeURIComponent(id)}/discard`, {}, () => 'Discarded.')}
		onRollback={(version) =>
			act('/rollback', { version }, (a) => `Version ${version} is current again, as version ${a['version']}.`)}
	/>
{:else}
	<p class="status">Reading {processId}…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
