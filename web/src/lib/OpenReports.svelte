<!--
	The start page's list of the reports that wait for an answer — decision requests, needs,
	dates, failures and alerts, daily signals — newest first, each leading to its page (DEC-0218,
	ADR-0120). It reads `GET /owner/reports` as the signed-in reader (ADR-0119). A reader who does not read the
	reports sees nothing of it: the section is the owner's and the people the owner named.
-->
<script lang="ts">
	import { read, surface } from './api';
	import { reportLink } from './links';
	import { KIND, openLine, openReports, type ReportList, type ReportView } from './reports';

	let { reports: given = null }: { reports?: ReportView[] | null } = $props();
	let fetched: ReportView[] | null = $state(null);
	const shown = $derived(given ?? fetched);
	const open = $derived(shown === null ? null : openReports(shown));

	$effect(() => {
		if (given !== null) return;
		void read<ReportList>(surface(location.href), 'owner/reports').then((answer) => {
			fetched = answer.ok ? answer.body.reports : null;
		});
	});
</script>

{#if open !== null}
	<section class="reports" aria-labelledby="open-reports">
		<h2 id="open-reports">Reports</h2>
		<p class="line">{openLine(open.length)}</p>
		{#if open.length}
			<ul>
				{#each open as r (r.id)}
					<li data-report={r.id}>
						<a href={reportLink(r.id)}>
							<span class="title">{r.title}</span>
							<span class="meta">{KIND[r.kind]} · {r.id} · needed by {r.due}{r.state === 'reflected' ? ' · read back, waiting for confirmation' : ''}</span>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{/if}

<style>
	.reports {
		margin-top: var(--sp-300);
	}
	.line {
		font-size: var(--fs-300);
		font-weight: var(--fw-medium);
		margin: 0 0 var(--sp-150);
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0;
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
		border-inline-start: 3px solid var(--accent-primary);
		text-decoration: none;
	}
	a:hover {
		background: var(--bg-surface-hover);
	}
	.title {
		font-weight: var(--fw-semibold);
	}
	.meta {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
</style>
