<!--
	The runs the reader may see, newest first, a page at a time (ADR-0321 §2): `GET /runs`, narrowed
	to a state and a process where the address names them (`#/runs?state=running&process=p`). Each
	row says its process, its state, whether it is a rehearsal and when it was created, and leads to
	the run. The first page is read again on every change of the frame's stream (ADR-0323 §2).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { failed, surface } from '../../lib/api';
	import EmptyState from '../../lib/EmptyState.svelte';
	import ErrorState from '../../lib/ErrorState.svelte';
	import { frame } from '../../lib/frame.svelte';
	import { processLink, runLink } from '../../lib/links';
	import { Rereader } from '../../lib/live';
	import { processOfRun, readRuns, RUN_STATES, when, type RunRow } from '../../lib/runs';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Skeleton from '../../lib/Skeleton.svelte';
	import type { Problem } from '../../lib/types';

	let signedIn = $state(true);
	let runs: RunRow[] | null = $state(null);
	let next: string | undefined = $state(undefined);
	let problem: Problem | null = $state(null);
	let more = $state(false);

	/** The query the address carries after `#/runs?`. */
	const query = $derived.by(() => {
		// Hash routing: the query sits in the address's hash, after the route.
		void page.url.href;
		const hash = typeof location === 'undefined' ? '' : location.hash;
		const at = hash.indexOf('?');
		const params = new URLSearchParams(at < 0 ? page.url.search : hash.slice(at + 1));
		return { state: params.get('state') ?? '', process: params.get('process') ?? '' };
	});

	const base = () => surface(location.href);
	async function first() {
		const found = await readRuns(base(), { state: query.state || undefined, process: query.process || undefined });
		if (found.ok) {
			runs = found.body.runs;
			next = found.body.next;
			problem = null;
		} else if (found.problem.status === 401) signedIn = false;
		else problem = found.problem;
	}
	const rereader = new Rereader(first);

	$effect(() => {
		void query.state;
		void query.process;
		runs = null;
		void rereader.request();
	});
	onMount(() => frame.subscribe((event) => event.kind === 'change' && next === undefined && void rereader.request()));

	async function readMore() {
		if (!next || !runs) return;
		more = true;
		const found = await readRuns(base(), { state: query.state || undefined, process: query.process || undefined, cursor: next });
		more = false;
		if (found.ok) {
			runs = [...runs, ...found.body.runs.filter((r) => !runs!.some((s) => s.id === r.id))];
			next = found.body.next;
		} else problem = found.problem;
	}

	function narrowed(state: string): string {
		const params = new URLSearchParams();
		if (state) params.set('state', state);
		if (query.process) params.set('process', query.process);
		const said = params.toString();
		return said ? `#/runs?${said}` : '#/runs';
	}
	const LABEL: Record<string, string> = { waiting_human: 'waiting on a person' };
</script>

{#if !signedIn}
	<SignInForm
		onSignedIn={() => {
			signedIn = true;
			void rereader.request();
		}}
	/>
{:else}
	<section aria-labelledby="runs-title">
		<p class="eyebrow">Work</p>
		<h1 id="runs-title">Runs{query.process ? ` of ${query.process}` : ''}</h1>
		<nav class="filters" aria-label="Narrow by state">
			<a href={narrowed('')} aria-current={query.state === '' ? 'page' : undefined}>All</a>
			{#each RUN_STATES as s (s)}
				<a href={narrowed(s)} aria-current={query.state === s ? 'page' : undefined}>{LABEL[s] ?? s}</a>
			{/each}
			{#if query.process}<a class="clear" href={query.state ? `#/runs?state=${query.state}` : '#/runs'}>Every process</a>{/if}
		</nav>

		{#if runs}
			{#if runs.length}
				<table class="runs" data-runs>
					<thead>
						<tr><th scope="col">Run</th><th scope="col">Process</th><th scope="col">State</th><th scope="col">Created</th></tr>
					</thead>
					<tbody>
						{#each runs as run (run.id)}
							<tr data-run={run.id}>
								<td data-label="Run"><a href={runLink(run.id)}>{run.id}</a></td>
								<td data-label="Process"><a href={processLink(run.process_version)}>{processOfRun(run)}</a></td>
								<td data-label="State"
									><span class="state state-{run.state}">{LABEL[run.state] ?? run.state}</span>{#if run.rehearsal}<span class="rehearsal">rehearsal</span>{/if}</td
								>
								<td data-label="Created"><time datetime={run.created_at}>{when(run.created_at)}</time></td>
							</tr>
						{/each}
					</tbody>
				</table>
				{#if next}
					<button type="button" onclick={readMore} disabled={more}>{more ? 'Reading…' : 'More runs'}</button>
				{/if}
			{:else}
				<EmptyState title={query.state || query.process ? 'No run you may see matches.' : 'No run you may see yet.'} />
			{/if}
		{:else if problem && failed(problem)}
			<ErrorState what="The runs" {problem} onRetry={() => void rereader.request()} />
		{:else if problem}
			<p role="alert">{problem.detail || problem.title}</p>
		{:else}
			<Skeleton label="Reading the runs…" lines={6} />
		{/if}
	</section>
{/if}

<style>
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-050);
		margin: var(--sp-200) 0 var(--sp-300);
	}
	.filters a {
		padding: var(--sp-050) var(--sp-150);
		border-radius: var(--r-full);
		border: var(--bw-hairline) solid var(--border-subtle);
		background: var(--bg-surface);
		text-decoration: none;
		font-size: var(--fs-090);
	}
	.filters a[aria-current='page'] {
		background: var(--accent-primary-subtle);
		border-color: var(--accent-primary);
		color: var(--text-brand);
		font-weight: var(--fw-semibold);
	}
	.runs {
		width: 100%;
		margin-bottom: var(--sp-200);
	}
	.state {
		display: inline-block;
		padding: 0 var(--sp-100);
		border-radius: var(--r-full);
		background: var(--status-neutral-surface);
		color: var(--status-neutral-text);
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
	}
	.state-running,
	.state-admitted {
		background: var(--status-info-surface);
		color: var(--status-info-text);
	}
	.state-finished {
		background: var(--status-success-surface);
		color: var(--status-success-text);
	}
	.state-escalated,
	.state-halted {
		background: var(--status-danger-surface);
		color: var(--status-danger-text);
	}
	.state-waiting_human {
		background: var(--status-warning-surface);
		color: var(--status-warning-text);
	}
	.rehearsal {
		margin-inline-start: var(--sp-100);
		font-size: var(--fs-075);
		font-style: italic;
		color: var(--text-secondary);
	}
	time {
		font-size: var(--fs-090);
		color: var(--text-secondary);
	}
	/* On a phone each run is a card: the cells stack, each with its label (ADR-0321 §4). */
	@media (max-width: 599px) {
		.runs thead {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
		}
		.runs,
		.runs tbody,
		.runs tr,
		.runs td {
			display: block;
		}
		.runs tr {
			padding: var(--sp-150) var(--sp-200);
			margin-bottom: var(--sp-100);
			border-radius: var(--r-lg);
			background: var(--bg-surface);
			border: var(--bw-hairline) solid var(--border-subtle);
		}
		.runs td {
			display: flex;
			justify-content: space-between;
			gap: var(--sp-200);
			padding: var(--sp-050) 0;
			border: none;
		}
		.runs td::before {
			content: attr(data-label);
			color: var(--text-subtle);
			font-size: var(--fs-075);
		}
	}
</style>
