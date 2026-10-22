<!--
	One report to the owner: the page every link a channel carries to it opens (UC-6.11, DEC-0218,
	ADR-0120). It reads `GET /owner/reports/{id}` as the signed-in reader, and asks for the key first
	when the reader is not signed in (ADR-0119). An answer goes to `POST /owner/reports/{id}/answer`, a confirmation to
	`…/confirm`. The page shows what the surface sends back and decides nothing itself.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, send, surface } from '../../../lib/api';
	import SignInForm from '../../../lib/SignInForm.svelte';
	import ReportPage from '../../../lib/ReportPage.svelte';
	import type { Answered, ReportView } from '../../../lib/reports';

	let signedIn = $state(true);
	let report: ReportView | null = $state(null);
	let missing: string | null = $state(null);
	let message: string | null = $state(null);
	let problem: string | null = $state(null);
	let busy = $state(false);

	const reportId = $derived(page.params.id ?? '');
	const path = $derived(`owner/reports/${encodeURIComponent(reportId)}`);

	function refuse(status: number): boolean {
		if (status !== 401) return false;
		signedIn = false;
		return true;
	}

	$effect(() => {
		if (!signedIn || !reportId) return;
		report = null;
		missing = null;
		message = null;
		problem = null;
		void read<ReportView>(surface(location.href), path).then((answer) => {
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
		if (!signedIn || !report) return;
		busy = true;
		const done = await send<Answered>(surface(location.href), `${path}/${route}`, body);
		busy = false;
		if (done.ok) {
			report = done.body.report;
			message = done.body.message || null;
			problem = null;
		} else if (!refuse(done.problem.status)) problem = done.problem.detail || done.problem.title;
	}
</script>

{#if !signedIn}
	<p class="lead">Sign in to read report {reportId}.</p>
	<SignInForm onSignedIn={() => (signedIn = true)} />
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
