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
	import { currentAdministrationKey } from '../../lib/governance';
	import { Rereader } from '../../lib/live';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Skeleton from '../../lib/Skeleton.svelte';
	import { KIND_WORD, readToday, type TodayData } from '../../lib/todayData';
	import type { Problem } from '../../lib/types';

	let signedIn = $state(true);
	let today = $state<TodayData | null>(null);
	let problem = $state<Problem | null>(null);

	const rereader = new Rereader(async () => {
		const found = await readToday(surface(location.href), currentAdministrationKey());
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
		<h1 id="waits-title">
			{today.waits.length === 0 ? 'Nothing waits for you.' : today.waits.length === 1 ? 'One item waits for you.' : `${today.waits.length} items wait for you.`}
		</h1>
		{#if today.waits.length}
			<ol class="waits">
				{#each today.waits as w (w.id)}
					<li data-wait={w.id} class:overdue={w.overdue}>
						<a href={w.href}>
							<span class="title">{w.title}</span>
							<span class="meta">{KIND_WORD[w.kind] ?? 'Report'} · {w.id}{w.due ? ` · needed by ${w.due}` : ''}{w.overdue ? ' · past its date' : ''}</span>
						</a>
					</li>
				{/each}
			</ol>
		{:else if today.counts.waiting_for_you === null}
			<ErrorState what="What waits for you" problem={{ status: 0, title: '', detail: 'Neither the decision requests nor the reports could be read.' }} onRetry={() => void rereader.request()} />
		{:else}
			<EmptyState title="Nothing waits for you.">
				<p>Decision requests addressed to you and open reports appear here.</p>
			</EmptyState>
		{/if}
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
	a {
		display: grid;
		gap: var(--sp-025);
		padding: var(--sp-150) var(--sp-200);
		border-radius: var(--r-lg);
		background: var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-inline-start: var(--bw-thick) solid var(--accent-primary);
		text-decoration: none;
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
