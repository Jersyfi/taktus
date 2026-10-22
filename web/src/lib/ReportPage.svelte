<!--
	One report to the owner, as the channel showed it (UC-6.11, DEC-0218, ADR-0120): what is
	needed, the steps, what stands still, by when, and how to answer. An answer — an offered one,
	or the reader's own words — takes no effect: its reading comes back, and only once the same
	reader confirms it is it filed (ADR-0008). The page sends what the reader chose and shows what
	the surface sent back; it decides nothing.
-->
<script lang="ts">
	import { answerLabel, KIND, standing, type ReportView } from './reports';

	let {
		report,
		message = null,
		busy = false,
		onAnswer,
		onConfirm
	}: {
		report: ReportView;
		/** The sentence the surface sent back after the last answer. */
		message?: string | null;
		busy?: boolean;
		onAnswer: (answer: { option: string } | { text: string }) => void;
		onConfirm: (confirmed: boolean) => void;
	} = $props();

	const open = $derived(report.state === 'open' || (report.state === 'reflected' && !report.reading?.by_you));
	const waitsForYou = $derived(report.state === 'reflected' && report.reading?.by_you === true);
	let own = $state('');

	function sendOwn(event: SubmitEvent) {
		event.preventDefault();
		if (own.trim()) onAnswer({ text: own.trim() });
		own = '';
	}
</script>

<article class="report" aria-labelledby="report-title" data-report={report.id} data-state={report.state}>
	<p class="eyebrow">{report.id} · {KIND[report.kind]}</p>
	<h1 id="report-title">{report.title}</h1>
	<p class="status">{standing(report)} · needed by {report.due}</p>

	<section>
		<h2>What is needed</h2>
		<ul>
			{#each report.needed as item, i (i)}<li>{item}</li>{/each}
		</ul>
	</section>

	<section>
		<h2>Steps</h2>
		<ol>
			{#each report.steps as step, i (i)}<li>{step}</li>{/each}
		</ol>
	</section>

	<section>
		<h2>What stands still</h2>
		<ul>
			{#each report.standing_still as item, i (i)}<li>{item}</li>{/each}
		</ul>
	</section>

	<section>
		<h2>By when</h2>
		<p>{report.due}. Without an answer the work above keeps standing still; nothing is decided for you.</p>
	</section>

	{#if report.links?.length}
		<section>
			<h2>Links</h2>
			<ul>
				{#each report.links as link (link.url)}<li><a href={link.url}>{link.label}</a></li>{/each}
			</ul>
		</section>
	{/if}

	<section>
		<h2>How to answer</h2>
		{#if report.state === 'filed' && report.filed}
			<p>Filed: {answerLabel(report, report.filed.answer)}, on {report.filed.at.slice(0, 10)}.</p>
		{:else}
			<ul class="offered">
				{#each report.offered as option (option.id)}
					<li class:recommended={option.recommended} data-offered={option.id}>
						<span>{option.label}</span>
						{#if option.recommended}<span class="tag">recommended</span>{/if}
						{#if open}
							<button type="button" disabled={busy} onclick={() => onAnswer({ option: option.id })}>Answer: {option.label}</button>
						{/if}
					</li>
				{/each}
			</ul>
			{#if open}
				<form class="own" onsubmit={sendOwn}>
					<label>
						Or answer in your own words, as in the channel
						<input type="text" bind:value={own} autocomplete="off" />
					</label>
					<button type="submit" disabled={busy || !own.trim()}>Send</button>
				</form>
			{/if}
		{/if}
	</section>

	{#if message || waitsForYou}
		<section class="reading" aria-live="polite">
			<h2>How your answer was read</h2>
			<p>{message ?? `Read as: ${answerLabel(report, report.reading?.answer ?? '')}.`}</p>
			{#if waitsForYou}
				<div class="row">
					<button type="button" class="primary" disabled={busy} onclick={() => onConfirm(true)}>Yes, that is what I mean</button>
					<button type="button" disabled={busy} onclick={() => onConfirm(false)}>No — answer again</button>
				</div>
				<p class="muted">Nothing is filed before you confirm how your answer was read.</p>
			{/if}
		</section>
	{/if}
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
	section ul,
	section ol {
		margin: 0.25rem 0;
		padding-left: 1.25rem;
	}
	.offered {
		list-style: none;
		padding: 0;
		display: grid;
		gap: 0.6rem;
	}
	.offered li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem;
		align-items: baseline;
		border: 1px solid var(--line);
		border-radius: 14px;
		padding: 0.8rem 1rem;
	}
	.offered li.recommended {
		border-color: var(--ink);
		box-shadow: inset 3px 0 0 var(--ink);
	}
	.offered li span:first-child {
		flex: 1;
		min-width: 10rem;
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
		margin-top: 0.4rem;
	}
</style>
