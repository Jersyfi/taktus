<!--
	A process changed in dialogue, and rolled back (UC-4.15, ADR-0091 §6). Reads the process level
	for its versions and the process's proposals; sends only the writes ADR-0091 §6 names, with the
	key in the header and nowhere else (ADR-0063 §4).
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, send, surface } from '../../../lib/api';
	import ChangeView from '../../../lib/ChangeView.svelte';
	import KeyForm from '../../../lib/KeyForm.svelte';
	import { currentKey } from '../../../lib/key';
	import type { ProcessLevel, Proposal } from '../../../lib/types';

	let key = $state(currentKey());
	let refused = $state(false);
	let absent = $state(false);
	let level: ProcessLevel | null = $state(null);
	let proposals: Proposal[] = $state([]);
	let message: string | null = $state(null);
	let busy = $state(false);

	const processId = $derived(page.params.id ?? '');
	const base = () => surface(location.href);
	const path = (rest: string) => `processes/${encodeURIComponent(processId)}${rest}`;

	async function reload() {
		if (!key) return;
		const [found, listed] = await Promise.all([
			read<ProcessLevel>(base(), `levels/${path('')}`, key),
			read<{ proposals: Proposal[] }>(base(), path('/proposals'), key)
		]);
		if (!found.ok) {
			if (found.problem.status === 401) {
				refused = true;
				key = null;
			} else absent = true;
			return;
		}
		level = found.body;
		proposals = listed.ok ? listed.body.proposals : [];
	}

	$effect(() => {
		if (key && processId) void reload();
	});

	async function act(rest: string, body: unknown, done: (answer: Record<string, unknown>) => string) {
		if (!key) return;
		busy = true;
		const answer = await send<Record<string, unknown>>(base(), path(rest), key, body);
		busy = false;
		if (answer.ok) message = done(answer.body);
		else if (answer.problem.status === 401) {
			refused = true;
			key = null;
		} else message = answer.problem.detail || answer.problem.title;
		await reload();
	}
</script>

{#if !key}
	<KeyForm {refused} onKey={(k) => (key = k)} />
{:else if absent}
	<p>No process {processId} you may see.</p>
{:else if level}
	<ChangeView
		{level}
		{proposals}
		{busy}
		{message}
		onAsk={(request) =>
			act('/proposals', { request }, (a) => `S-07 is working out your change in run ${a['run']}. The proposal appears here.`)}
		onRehearse={(id) =>
			act(`/proposals/${encodeURIComponent(id)}/rehearse`, {}, (a) => `Rehearsing in run ${a['run']}; nothing leaves the system.`)}
		onCommission={(id) =>
			act(`/proposals/${encodeURIComponent(id)}/commission`, {}, (a) => `Version ${a['version']} is registered and active.`)}
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
