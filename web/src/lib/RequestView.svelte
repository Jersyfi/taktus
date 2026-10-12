<!--
	One decision request addressed to the reader (UC-7.4, ADR-0042), and the answer to it. The
	request says what happened, what is to be decided, the options with one recommended and why,
	what is blocked and by when. An answer — an option, or the reader's own words — takes no effect:
	the reading comes back, and only once the reader confirms it does it take effect (ADR-0008).
	The page sends what the reader chose and shows what the surface sent back; it decides nothing.
-->
<script lang="ts">
	import { runLink } from './links';
	import type { AddressedRequest } from './types';

	let {
		addressed,
		message = null,
		busy = false,
		onAnswer,
		onConfirm
	}: {
		addressed: AddressedRequest;
		/** The message the surface sent back after the last answer. */
		message?: string | null;
		busy?: boolean;
		onAnswer: (answer: { option: string } | { text: string }) => void;
		onConfirm: (confirmed: boolean) => void;
	} = $props();

	const request = $derived(addressed.request);
	const STATUS: Record<string, string> = {
		open: 'open, waiting for your answer',
		answered: 'answered',
		interpreted: 'answered, its reading sent back',
		confirmed: 'its reading confirmed',
		applied: 'applied'
	};
	let own = $state('');

	function sendOwn(event: SubmitEvent) {
		event.preventDefault();
		if (own.trim()) onAnswer({ text: own.trim() });
		own = '';
	}
</script>

<article class="request" aria-labelledby="request-title" data-request={request.id}>
	<p class="eyebrow">
		{request.id} · raised in <a href={runLink(request.raised_by.run)}>{request.raised_by.run}</a>, step
		{request.raised_by.step}
	</p>
	<h1 id="request-title">{request.question}</h1>
	<p class="status" data-status={request.status}>
		{STATUS[request.status] ?? request.status}{#if addressed.overdue}&#32;· <strong>past its date</strong>{/if}
	</p>

	<section>
		<h2>What happened</h2>
		<p>{request.situation}</p>
	</section>

	<section>
		<h2>Options</h2>
		<ul class="options">
			{#each request.options as option (option.id)}
				<li class:recommended={option.recommended} data-option={option.id}>
					<div class="proposal">
						<strong>{option.id} — {option.proposal}</strong>
						{#if option.recommended}<span class="tag">recommended</span>{/if}
					</div>
					{#if option.consequence}<p>{option.consequence}</p>{/if}
					{#if option.effort}<p class="muted">Effort: {option.effort}</p>{/if}
					{#if option.recommended && option.reason}<p class="muted">Why: {option.reason}</p>{/if}
					{#if request.status === 'open'}
						<button type="button" disabled={busy} onclick={() => onAnswer({ option: option.id })}>Choose {option.id}</button>
					{/if}
				</li>
			{/each}
		</ul>
		{#if request.status === 'open'}
			<form class="own" onsubmit={sendOwn}>
				<label>
					Or answer in your own words
					<input type="text" bind:value={own} autocomplete="off" />
				</label>
				<button type="submit" disabled={busy || !own.trim()}>Send</button>
			</form>
		{/if}
	</section>

	{#if message || (request.status === 'interpreted' && addressed.answered_by_you)}
		<section class="reading" aria-live="polite">
			<h2>How your answer was read</h2>
			<p>{message ?? addressed.reflection}</p>
			{#if request.status === 'interpreted' && addressed.answered_by_you}
				<div class="row">
					<button type="button" class="primary" disabled={busy} onclick={() => onConfirm(true)}>Yes, that is what I mean</button>
					<button type="button" disabled={busy} onclick={() => onConfirm(false)}>No — answer again</button>
				</div>
				<p class="muted">Nothing takes effect before you confirm how your answer was read.</p>
			{/if}
		</section>
	{/if}

	<section>
		<h2>What is blocked</h2>
		<p>{request.blocking.length ? request.blocking.join(', ') : 'Nothing else.'}</p>
	</section>

	<section>
		<h2>By when</h2>
		<p>{request.due}. Without an answer the run keeps waiting; nothing is decided for you.</p>
	</section>
</article>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	.status,
	.muted {
		color: var(--ink-2);
	}
	section {
		border-top: 1px solid var(--line);
		padding: 0.9rem 0;
		max-width: 46rem;
	}
	section p {
		margin: 0.25rem 0;
	}
	.options {
		list-style: none;
		padding: 0;
		display: grid;
		gap: 0.6rem;
	}
	.options li {
		border: 1px solid var(--line);
		border-radius: 14px;
		padding: 0.8rem 1rem;
	}
	.options li.recommended {
		border-color: var(--ink);
		box-shadow: inset 3px 0 0 var(--ink);
	}
	.proposal {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		align-items: baseline;
	}
	.tag {
		font-family: var(--mono);
		font-size: 0.7rem;
		border: 1px solid var(--ink);
		border-radius: 5px;
		padding: 0 0.35rem;
		white-space: nowrap;
	}
	button {
		font: inherit;
		border: 1px solid var(--line);
		background: var(--paper);
		color: var(--ink);
		border-radius: 10px;
		padding: 0.4rem 0.9rem;
		cursor: pointer;
		margin-top: 0.4rem;
	}
	button.primary {
		background: var(--ink);
		color: var(--paper);
		border-color: var(--ink);
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.own {
		display: flex;
		gap: 0.5rem;
		align-items: end;
		margin-top: 0.75rem;
		flex-wrap: wrap;
	}
	.own label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1;
		min-width: 14rem;
	}
	.own input {
		font: inherit;
		padding: 0.45rem 0.7rem;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: var(--paper);
		color: var(--ink);
	}
	.reading {
		background: var(--paper-2);
		border-radius: 14px;
		border-top: none;
		padding: 1rem 1.1rem;
	}
	.row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
</style>
