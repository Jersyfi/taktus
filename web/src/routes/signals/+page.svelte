<!--
	The signals: `GET /signals`, and the newest daily report from `GET /signals/daily-report`,
	each read once on opening (ADR-0121, ADR-0109). The daily report is read by the owner and the
	people the owner named; for anyone else the page says so, and shows the signals.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { DailyReport, SignalRecord } from '../../lib/operation';
	import SignalsView from '../../lib/SignalsView.svelte';

	let signedIn = $state(true);
	let found: SignalRecord[] | null = $state(null);
	let daily: DailyReport | null = $state(null);
	let dailyNote: string | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		const base = surface(location.href);
		void read<{ signals: SignalRecord[] }>(base, 'signals').then((answer) => {
			if (answer.ok) found = answer.body.signals;
			else if (answer.problem.status === 401) {
				signedIn = false;
			} else problem = answer.problem.detail || answer.problem.title;
		});
		void read<DailyReport>(base, 'signals/daily-report').then((answer) => {
			if (answer.ok) daily = answer.body;
			else if (answer.problem.status === 403)
				dailyNote = 'The owner and the people the owner named read the daily report.';
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if found}
	<SignalsView signals={found} {daily} {dailyNote} />
{:else if problem}
	<p class="status">{problem}</p>
{:else}
	<p class="status">Reading the signals…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
