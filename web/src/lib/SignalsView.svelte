<!--
	The signals (ADR-0109, UC-6.13): each judged now against its corridor — red and yellow first,
	then those not measured with the reason, then the normal ones — with the run and the step that
	measured it, its process, the role a red value reaches and where a deviation is worked. A
	corridor names the operation, a role or a department, never a person. Below, the newest daily
	report, for the owner and the people the owner named.
-->
<script lang="ts">
	import { processLink, runLink } from './links';
	import { moment, signalsSentence, webAddress, type DailyReport, type SignalRecord } from './operation';
	import OperationPage from './OperationPage.svelte';

	let {
		signals,
		daily = null,
		dailyNote = null
	}: { signals: SignalRecord[]; daily?: DailyReport | null; dailyNote?: string | null } = $props();

	const ORDER: Record<string, number> = { red: 0, yellow: 1, unmeasured: 2, normal: 3 };
	const LEVEL: Record<string, string> = {
		red: 'Red',
		yellow: 'Yellow',
		unmeasured: 'Not measured',
		normal: 'Within its corridor'
	};
	const REASON: Record<string, string> = {
		failed: 'its newest attempt failed',
		not_admissible: 'its newest value is no measurement',
		not_a_number: 'its newest value is no number',
		no_measurement: 'no attempt within its freshness',
		too_little_history: 'too little history for its median'
	};
	const ordered = $derived([...signals].sort((a, b) => ORDER[a.level]! - ORDER[b.level]! || a.signal.localeCompare(b.signal)));
	const sentence = $derived(signalsSentence(signals));

	function about(s: SignalRecord): string {
		return s.about.kind === 'operation' ? 'the operation' : `${s.about.kind} ${s.about.name}`;
	}
	function threshold(s: SignalRecord, which: 'yellow' | 'red'): string {
		const bound = s[which];
		const at = which === 'yellow' ? s.yellow_at : s.red_at;
		const side = s.direction === 'above' ? 'above' : 'below';
		if (s.bounds === 'median') return `${side} ${bound} × median${at != null ? ` (${at})` : ''}`;
		return `${side} ${bound}`;
	}
	function line(s: SignalRecord): string {
		const head = `${s.signal} (${about(s)}): ${LEVEL[s.level]!.toLowerCase()}`;
		if (s.level === 'unmeasured') return `${head}, ${REASON[s.reason ?? ''] ?? s.reason}.`;
		return `${head}, ${s.value} at ${moment(s.at)}, yellow ${threshold(s, 'yellow')}, red ${threshold(s, 'red')}, run ${s.run_id}, step ${s.step_id}.`;
	}
	const dailyLines = $derived(daily ? [`Daily report ${daily.id}: ${daily.title}.`, ...daily.needed] : []);
</script>

<OperationPage eyebrow="Signals" {sentence} lines={[...ordered.map(line), ...dailyLines]}>
	{#if ordered.length}
		<ul class="records">
			{#each ordered as s (s.signal)}
				<li class="record" class:look={s.level === 'red'} data-signal={s.signal} data-level={s.level}>
					<p
						class="mark"
						class:look={s.level === 'red'}
						class:half={s.level === 'yellow'}
						class:unknown={s.level === 'unmeasured'}
					>
						{LEVEL[s.level]}
					</p>
					<h3>{s.signal}</h3>
					<p class="meta">About {about(s)}; a red value reaches the role {s.role}.</p>
					<dl class="facts">
						{#if s.level === 'unmeasured'}
							<dt>Why</dt><dd>{REASON[s.reason ?? ''] ?? s.reason}</dd>
						{:else}
							<dt>Value</dt><dd>{s.value}{#if s.median != null} (median {s.median}){/if}</dd>
							<dt>Measured</dt><dd>{moment(s.at)}</dd>
						{/if}
						<dt>Yellow</dt><dd>{threshold(s, 'yellow')}</dd>
						<dt>Red</dt><dd>{threshold(s, 'red')}</dd>
						<dt>Process</dt>
						<dd><a href={processLink(s.process_version ?? s.process)}>{s.process_version ?? s.process}</a>, step {s.step}</dd>
						{#if s.run_id}
							<dt>Run</dt><dd><a href={runLink(s.run_id)}>{s.run_id}</a>{#if s.step_id}, step {s.step_id}{/if}</dd>
						{/if}
						<dt>Case</dt>
						<dd>{#if webAddress(s.case)}<a href={webAddress(s.case)} rel="noopener noreferrer">{s.case}</a>{:else}{s.case}{/if}</dd>
						<dt>Corridor</dt><dd>{s.corridor}, since {moment(s.changed_at)}</dd>
					</dl>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="empty">No corridor is in force: no signal is judged.</p>
	{/if}

	<section class="daily" aria-labelledby="daily-title">
		<h2 id="daily-title">The newest daily report</h2>
		{#if daily}
			<div class="record" data-daily={daily.id}>
				<h3>{daily.title}</h3>
				<p class="meta">Raised {moment(daily.raised_at)}.</p>
				<ul>
					{#each daily.needed as n, i (i)}<li>{n}</li>{/each}
				</ul>
				<p class="meta">{daily.standing_still.join(' ')}</p>
				<p class="id">{daily.id}</p>
			</div>
		{:else}
			<p class="empty">{dailyNote ?? 'No daily report was raised yet.'}</p>
		{/if}
	</section>
</OperationPage>

<style>
	.daily {
		margin-top: 2.5rem;
		max-width: 44rem;
	}
	.daily ul {
		padding-left: 1.1rem;
		font-size: 0.9rem;
	}
</style>
