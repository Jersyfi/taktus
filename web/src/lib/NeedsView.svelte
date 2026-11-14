<!--
	The needs among the reports to the owner (ADR-0028, ADR-0045, ADR-0122): what only the owner
	can provide, the steps to provide it, what stands still for want of it, by when, its state and
	the answer filed. Read from `GET /owner/reports`, by the owner and whom the owner named. The
	history says whether the reader acted, never who did. The decision requests have their own page.
	Each need leads to its report's page, where it is answered as in the channel (ADR-0120).
-->
<script lang="ts">
	import DisplaySwitch from './DisplaySwitch.svelte';
	import TextEquivalent from './TextEquivalent.svelte';
	import { display } from './display.svelte';
	import type { OwnerReport } from './governance';
	import { reportLink, requestsLink } from './links';

	let { needs }: { needs: OwnerReport[] } = $props();

	const open = $derived(needs.filter((n) => n.state !== 'filed'));
	const STATE: Record<string, string> = {
		open: 'open, waiting for the owner',
		reflected: 'answered, its reading sent back to confirm',
		filed: 'provided'
	};
	const sentence = $derived(
		open.length === 0 ? 'No need is open.' : `${open.length} ${open.length === 1 ? 'need is' : 'needs are'} open.`
	);
</script>

<section class="needs" aria-labelledby="needs-title">
	<p class="eyebrow">Needs</p>
	<h1 id="needs-title">{sentence}</h1>
	<p class="muted">What only the owner can provide. The questions to decide are the <a href={requestsLink()}>decision requests</a>.</p>

	<ul class="list">
		{#each needs as n (n.id)}
			<li class="need" class:filed={n.state === 'filed'} data-need={n.id} data-state={n.state}>
				<p class="id">{n.id} · due {n.due}</p>
				<h2 class="title"><a href={reportLink(n.id)}>{n.title}</a></h2>
				<p class="state">{STATE[n.state] ?? n.state}</p>
				<div class="grid">
					<div>
						<h3>Needed</h3>
						<ul>{#each n.needed as x (x)}<li>{x}</li>{/each}</ul>
					</div>
					<div>
						<h3>Steps</h3>
						<ol>{#each n.steps as x (x)}<li>{x}</li>{/each}</ol>
					</div>
					<div>
						<h3>Stands still</h3>
						<ul>{#each n.standing_still as x (x)}<li>{x}</li>{/each}</ul>
					</div>
				</div>
				{#if n.filed}
					<p class="answer">Provided: {n.filed.answer}{n.filed.by_you ? ', by you' : ''}, {n.filed.at.slice(0, 10)}.</p>
				{:else if n.reading}
					<p class="answer">Read as “{n.reading.answer}”; waiting for {n.reading.by_you ? 'your' : 'its'} confirmation.</p>
				{/if}
				{#if n.state !== 'filed'}
					<a class="link answer-link" href={reportLink(n.id)}>Answer it on its page</a>
				{/if}
				{#each n.links ?? [] as l (l.url)}
					<a class="link" href={l.url}>{l.label}</a>
				{/each}
			</li>
		{/each}
	</ul>

	<div class="as-text"><DisplaySwitch page="needs" /></div>
	<TextEquivalent label="The needs as text" mode={display.of('needs')}>
			<li>{sentence}</li>
			{#each needs as n (n.id)}
				<li data-text="need:{n.id}">{n.id}: {n.title}; {STATE[n.state] ?? n.state}; due {n.due}.</li>
			{/each}
	</TextEquivalent>
</section>

<style>
	.as-text {
		display: flex;
		justify-content: flex-end;
		margin-top: var(--sp-400);
	}
	.muted,
	.state,
	.id {
		color: var(--text-secondary);
		font-size: var(--fs-100);
		margin: 0.2rem 0;
	}
	.id {
		font-family: var(--font-mono);
		font-size: var(--fs-075);
	}
	.list {
		list-style: none;
		padding: 0;
		display: grid;
		gap: 0.9rem;
		max-width: 56rem;
	}
	.need {
		border-radius: var(--r-2xl);
		padding: 1rem 1.2rem;
		background: var(--bg-surface);
		box-shadow: inset 3px 0 0 var(--text-primary);
	}
	/* A need provided rests: no edge, quieter ink. */
	.need.filed {
		box-shadow: none;
		color: var(--text-secondary);
	}
	.title a {
		text-decoration: none;
	}
	.title {
		font-size: var(--fs-200);
		font-weight: 600;
		letter-spacing: 0;
		text-transform: none;
		color: inherit;
		margin: 0.2rem 0;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr));
		gap: 1rem;
	}
	h3 {
		font-size: var(--fs-075);
		font-weight: 500;
		color: var(--text-subtle);
		margin: 0.6rem 0 0.2rem;
	}
	.grid ul,
	.grid ol {
		margin: 0;
		padding-left: 1.1rem;
		font-size: var(--fs-100);
	}
	.answer {
		font-size: var(--fs-100);
	}
	.link {
		font-size: var(--fs-100);
		margin-right: 0.75rem;
	}
</style>
