<!--
	Everything that waits for the reader, in one list (ADR-0321 §4): the decision requests addressed
	to them and the open reports, each once, oldest due first. Today shows the first five; a phone's
	bottom bar leads here. Read through `todayData.ts`, again on every change of the frame's stream.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { failed, surface } from '../../lib/api';
	import EmptyState from '../../lib/EmptyState.svelte';
	import ErrorState from '../../lib/ErrorState.svelte';
	import { frame } from '../../lib/frame.svelte';
	import { Rereader } from '../../lib/live';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Skeleton from '../../lib/Skeleton.svelte';
	import { when } from '../../lib/runs';
	import { KIND_WORD, readToday, type TodayData } from '../../lib/todayData';
	import type { Problem } from '../../lib/types';

	let signedIn = $state(true);
	let today = $state<TodayData | null>(null);
	let problem = $state<Problem | null>(null);

	function waitsHeading(n: number | null): string {
		if (n === null) return 'What waits for you';
		return n === 0 ? 'Nothing waits for you.' : n === 1 ? 'One item waits for you.' : `${n} items wait for you.`;
	}

	const rereader = new Rereader(async () => {
		const found = await readToday(surface(location.href));
		if (found.ok) {
			today = found.today;
			problem = null;
		} else if (found.problem.status === 401) signedIn = false;
		else problem = found.problem;
	});

	onMount(() => {
		void rereader.request();
		return frame.subscribe(() => void rereader.request());
	});
</script>

{#if !signedIn}
	<SignInForm
		onSignedIn={() => {
			signedIn = true;
			void rereader.request();
		}}
	/>
{:else if today}
	<section aria-labelledby="waits-title">
		<p class="eyebrow">For you</p>
		<h1 id="waits-title">{waitsHeading(today.counts.waiting_for_you)}</h1>
		{#if today.waits.length}
			<h2>The most urgent</h2>
			<ol class="waits">
				{#each today.waits as w (w.link + w.since)}
					<li data-wait={w.link} class:overdue={w.urgent}>
						<a href={w.link}>
							<span class="title">{w.title}</span>
							<span class="meta">{KIND_WORD[w.kind] ?? 'Report'}{w.since ? ` · since ${when(w.since)}` : ''}{w.urgent ? ' · urgent' : ''}</span>
						</a>
					</li>
				{/each}
			</ol>
		{:else}
			<EmptyState title="Nothing waits for you.">
				<p>Decision requests addressed to you, open needs and reports, alerts and failures of the last day appear here.</p>
			</EmptyState>
		{/if}
		<!-- The surface lists the five most urgent; every one of a kind is on its own page. -->
		<h2>Every one, by kind</h2>
		<ul class="kinds">
			{#each today.lines as line (line.kind)}
				<li><a href={line.href}>{line.text}</a></li>
			{/each}
			{#if today.counts.open_alerts !== null}
				<li><a href="#/alerts">Alerts: {today.counts.open_alerts} in effect.</a></li>
			{/if}
			{#if today.counts.failed_last_24h !== null}
				<li><a href="#/runs?state=escalated">Failures: {today.counts.failed_last_24h} in the last 24 hours.</a></li>
			{/if}
		</ul>
	</section>
{:else if problem && failed(problem)}
	<ErrorState what="What waits for you" {problem} onRetry={() => void rereader.request()} />
{:else if problem}
	<p role="alert">{problem.detail || problem.title}</p>
{:else}
	<Skeleton label="Reading what waits for you…" />
{/if}

<style>
	.waits {
		list-style: none;
		padding: 0;
		margin: var(--sp-300) 0 0;
		display: grid;
		gap: var(--sp-100);
		max-width: 52rem;
	}
	.waits a {
		display: grid;
		gap: var(--sp-025);
		padding: var(--sp-150) var(--sp-200);
		border-radius: var(--r-lg);
		background: var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-inline-start: var(--bw-thick) solid var(--accent-primary);
		text-decoration: none;
	}
	.kinds {
		list-style: none;
		padding: 0;
		display: grid;
		gap: var(--sp-050);
	}
	.overdue a {
		border-inline-start-color: var(--family-alert);
	}
	.title {
		font-weight: var(--fw-semibold);
	}
	.meta {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
</style>
