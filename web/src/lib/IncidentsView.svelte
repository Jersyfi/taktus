<!--
	The incidents (ADR-0107, UC-4.16): what was expected and what happened, the open ones first.
	Each links the process version it is about and every run it names; nothing names a person.
-->
<script lang="ts">
	import { processLink, runLink } from './links';
	import { incidentsSentence, moment, type IncidentRecord } from './operation';
	import OperationPage from './OperationPage.svelte';

	let { incidents }: { incidents: IncidentRecord[] } = $props();

	const KINDS: Record<string, string> = {
		'run.missing': 'An expected run did not happen',
		'run.overdue': 'A run did not end in time',
		'signal.red': 'A signal is red',
		'anchor.breach': 'An anchor was breached',
		'corrections.rate': 'Corrections rose above the limit'
	};
	const WHAT: Record<string, string> = {
		missed: 'missed',
		happened: 'a run happened',
		closed: 'closed',
		red: 'red again'
	};

	const ordered = $derived([
		...incidents.filter((i) => i.state === 'open'),
		...incidents.filter((i) => i.state !== 'open')
	]);
	const sentence = $derived(incidentsSentence(incidents));

	function title(i: IncidentRecord): string {
		return KINDS[i.kind] ?? i.kind;
	}
	function line(i: IncidentRecord): string {
		const parts = [`${i.id} (${i.state}): ${title(i)}, ${i.process_version}, rule ${i.rule}`];
		if (i.expected_at) parts.push(`expected ${moment(i.expected_at)}`);
		if (i.run_id) parts.push(`run ${i.run_id}`);
		if (i.last_run?.run_id) parts.push(`last run ${i.last_run.run_id}`);
		parts.push(`raised ${moment(i.raised_at)}`);
		if (i.closed_at) parts.push(`closed ${moment(i.closed_at)}`);
		return `${parts.join('; ')}.`;
	}
</script>

<OperationPage eyebrow="Incidents" {sentence} lines={ordered.map(line)}>
	{#if ordered.length}
		<ul class="records">
			{#each ordered as i (i.id)}
				<li class="record" class:look={i.state === 'open'} class:done={i.state !== 'open'} data-incident={i.id}>
					<p class="mark" class:look={i.state === 'open'}>{i.state === 'open' ? 'Open' : 'Closed'}</p>
					<h3>{title(i)}</h3>
					<p class="meta">
						Process <a href={processLink(i.process_version)}>{i.process_version}</a>
					</p>
					<dl class="facts">
						{#if i.expected_at}<dt>Expected</dt><dd>{moment(i.expected_at)}</dd>{/if}
						{#if i.run_id}
							<dt>Run</dt>
							<dd>
								<a href={runLink(i.run_id)}>{i.run_id}</a>{#if i.step_id}, step {i.step_id}{/if}
							</dd>
						{/if}
						<dt>Last run</dt>
						<dd>
							{#if i.last_run?.run_id}
								<a href={runLink(i.last_run.run_id)}>{i.last_run.run_id}</a> at {moment(i.last_run.at)}
							{:else if i.last_run}
								a firing that found nothing, at {moment(i.last_run.at)}
							{:else}
								none recorded
							{/if}
						</dd>
						<dt>Rule</dt><dd>{i.rule}</dd>
						<dt>Raised</dt><dd>{moment(i.raised_at)}</dd>
						{#if i.closed_at}<dt>Closed</dt><dd>{moment(i.closed_at)}</dd>{/if}
					</dl>
					{#if i.timeline.length}
						<details>
							<summary>What happened since</summary>
							<ul>
								{#each i.timeline as h, n (n)}
									<li>
										{moment(h.at)}: {WHAT[h.what] ?? h.what}{#if h.expected_at && h.what === 'missed'}, expected {moment(h.expected_at)}{/if}{#if h.run_id},
											run <a href={runLink(h.run_id)}>{h.run_id}</a>{/if}
									</li>
								{/each}
							</ul>
						</details>
					{/if}
					<p class="id">{i.id}</p>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="empty">The watch over expected runs raised nothing.</p>
	{/if}
</OperationPage>
