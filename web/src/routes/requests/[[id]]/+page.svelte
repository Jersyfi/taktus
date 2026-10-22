<!--
	The decision requests addressed to the reader, and one of them answered (UC-6.11's view in the
	web app, UC-7.4, ADR-0042, ADR-0063 §4 as amended). The list is read from `GET /decisions`; an
	answer goes to `POST /decisions/{id}/answer`, a confirmation to `…/confirm`. The page shows
	what the surface sends back and decides nothing itself.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { read, send, surface } from '../../../lib/api';
	import SignInForm from '../../../lib/SignInForm.svelte';
	import { requestsLink } from '../../../lib/links';
	import RequestView from '../../../lib/RequestView.svelte';
	import type { AddressedList, AddressedRequest } from '../../../lib/types';

	let signedIn = $state(true);
	let list: AddressedList | null = $state(null);
	let chosen: AddressedRequest | null = $state(null);
	let absent = $state(false);
	let message: string | null = $state(null);
	let problem: string | null = $state(null);
	let busy = $state(false);

	const requestId = $derived(page.params.id ?? '');

	function refuse(status: number): boolean {
		if (status !== 401) return false;
		signedIn = false;
		return true;
	}

	$effect(() => {
		if (!signedIn) return;
		const base = surface(location.href);
		message = null;
		problem = null;
		void read<AddressedList>(base, 'decisions').then((answer) => {
			if (answer.ok) list = answer.body;
			else refuse(answer.problem.status);
		});
		if (!requestId) {
			chosen = null;
			return;
		}
		absent = false;
		void read<AddressedRequest>(base, `decisions/${encodeURIComponent(requestId)}`).then((answer) => {
			if (answer.ok) chosen = answer.body;
			else if (!refuse(answer.problem.status)) absent = true;
		});
	});

	async function answer(given: { option: string } | { text: string }) {
		if (!signedIn || !chosen) return;
		busy = true;
		const path = `decisions/${encodeURIComponent(chosen.id)}/answer`;
		const answered = await send<{ message: string; request: AddressedRequest }>(surface(location.href), path, given);
		busy = false;
		if (answered.ok) {
			message = answered.body.message;
			chosen = answered.body.request;
			problem = null;
		} else if (!refuse(answered.problem.status)) problem = answered.problem.detail || answered.problem.title;
	}

	async function confirm(confirmed: boolean) {
		if (!signedIn || !chosen) return;
		busy = true;
		const path = `decisions/${encodeURIComponent(chosen.id)}/confirm`;
		const done = await send<{ applied: boolean; request: AddressedRequest }>(surface(location.href), path, { confirmed });
		busy = false;
		if (done.ok) {
			chosen = done.body.request;
			message = done.body.applied ? 'Applied. The run continues at its step boundary.' : 'Not applied. The request is open again.';
			problem = null;
		} else if (!refuse(done.problem.status)) problem = done.problem.detail || done.problem.title;
	}
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else}
	<div class="requests">
		<nav aria-label="Decision requests addressed to you">
			<p class="eyebrow">Requests</p>
			{#if list === null}
				<p class="muted">Reading the requests addressed to you…</p>
			{:else if list.requests.length === 0}
				<p>Nothing waits for you.</p>
			{:else}
				<ul>
					{#each list.requests as r (r.id)}
						<li>
							<a href={requestsLink(r.id)} aria-current={r.id === requestId ? 'page' : undefined}>
								<span class="id">{r.id}</span>
								<span>{r.request.question}</span>
								<span class="muted">due {r.request.due}{r.overdue ? ' · past its date' : ''}</span>
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</nav>
		<div>
			{#if problem}<p role="alert">{problem}</p>{/if}
			{#if !requestId}
				{#if list}
					<h1>
						{list.requests.length === 0
							? 'Nothing waits for you.'
							: `${list.requests.length} ${list.requests.length === 1 ? 'question waits' : 'questions wait'} for you.`}
					</h1>
					<p class="muted">None is an alarm: each one is a planned question, with an answer proposed.</p>
				{/if}
			{:else if absent}
				<p>No request {requestId} addressed to you.</p>
			{:else if chosen}
				<RequestView addressed={chosen} {message} {busy} onAnswer={answer} onConfirm={confirm} />
			{:else}
				<p class="muted">Reading {requestId}…</p>
			{/if}
		</div>
	</div>
{/if}

<style>
	.requests {
		display: grid;
		grid-template-columns: 18rem minmax(0, 1fr);
		gap: 2rem;
		align-items: start;
	}
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	nav ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.3rem;
	}
	nav a {
		display: grid;
		gap: 0.1rem;
		padding: 0.6rem 0.75rem;
		border-radius: 12px;
		text-decoration: none;
	}
	nav a:hover,
	nav a[aria-current='page'] {
		background: var(--paper-2);
	}
	.id {
		font-family: var(--mono);
		font-size: 0.75rem;
		color: var(--ink-3);
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.85rem;
	}
	@media (max-width: 760px) {
		.requests {
			grid-template-columns: 1fr;
		}
	}
</style>
