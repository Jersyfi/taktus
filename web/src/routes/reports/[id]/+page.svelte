<!--
	One report to the owner: the page every link a channel carries to it opens (UC-6.11, DEC-0218,
	ADR-0120). It reads `GET /owner/reports/{id}` with the tab's key, and asks for the key first
	when the tab holds none. An answer goes to `POST /owner/reports/{id}/answer`, a confirmation to
	`…/confirm`. The page shows what the surface sends back and decides nothing itself.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, send, surface } from '../../../lib/api';
	import KeyForm from '../../../lib/KeyForm.svelte';
	import { currentKey } from '../../../lib/key';
	import ReportPage from '../../../lib/ReportPage.svelte';
	import type { Answered, ReportView } from '../../../lib/reports';

	let key = $state(currentKey());
	let refused = $state(false);
	let report: ReportView | null = $state(null);
	let missing: string | null = $state(null);
	let message: string | null = $state(null);
	let problem: string | null = $state(null);
	let busy = $state(false);

	const reportId = $derived(page.params.id ?? '');
	const path = $derived(`owner/reports/${encodeURIComponent(reportId)}`);

	function refuse(status: number): boolean {
		if (status !== 401) return false;
		refused = true;
		key = null;
		return true;
	}

	$effect(() => {
		if (!key || !reportId) return;
		report = null;
		missing = null;
		message = null;
		problem = null;
		void read<ReportView>(surface(location.href), path, key).then((answer) => {
			if (answer.ok) report = answer.body;
			else if (!refuse(answer.problem.status))
				missing =
					answer.problem.status === 403
						? 'Only the owner, and the people the owner named, read the reports.'
						: answer.problem.status === 404
							? `No report ${reportId}.`
							: answer.problem.detail || answer.problem.title;
		});
	});

	async function act(route: 'answer' | 'confirm', body: unknown) {
		if (!key || !report) return;
		busy = true;
		const done = await send<Answered>(surface(location.href), `${path}/${route}`, key, body);
		busy = false;
		if (done.ok) {
			report = done.body.report;
			message = done.body.message || null;
			problem = null;
		} else if (!refuse(done.problem.status)) problem = done.problem.detail || done.problem.title;
	}
</script>

{#if !key}
	<p class="lead">Give your account key to read report {reportId}.</p>
	<KeyForm {refused} onKey={(k) => (key = k)} />
{:else if missing}
	<p role="alert">{missing}</p>
	<p><a href="#/">Back to the overview</a></p>
{:else if report}
	{#if problem}<p role="alert">{problem}</p>{/if}
	<ReportPage
		{report}
		{message}
		{busy}
		onAnswer={(given) => act('answer', given)}
		onConfirm={(confirmed) => act('confirm', { confirmed })}
	/>
{:else}
	<p class="muted">Reading {reportId}…</p>
{/if}

<style>
	.lead {
		font-family: var(--serif);
		font-size: 1.4rem;
		margin: 0 0 1rem;
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.85rem;
	}
</style>
