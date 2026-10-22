<!--
	The alerts (ADR-0106): what needs a person's action, those in effect first, each with what
	became of its report and the runs, steps and process versions it is about. An alert about the
	backup leads to the backup's page. Read by the owner and the people the owner named.
-->
<script lang="ts">
	import { processLink, runLink } from './links';
	import { alertsSentence, backupLink, moment, type AlertRecord } from './operation';
	import OperationPage from './OperationPage.svelte';

	let { alerts }: { alerts: AlertRecord[] } = $props();

	const live = (a: AlertRecord) => a.in_effect && !a.closed;
	const ordered = $derived([...alerts.filter(live), ...alerts.filter((a) => !live(a))]);
	const sentence = $derived(alertsSentence(alerts));

	function standing(a: AlertRecord): string {
		if (a.closed) return 'Closed';
		return a.in_effect ? 'In effect' : 'Cleared';
	}
</script>

<OperationPage
	eyebrow="Alerts"
	{sentence}
	lines={ordered.map((a) => `${a.id} (${standing(a).toLowerCase()}): ${a.summary} Report: ${a.state}.`)}
>
	{#if ordered.length}
		<ul class="records">
			{#each ordered as a (a.id)}
				<li class="record" class:look={live(a)} class:done={!live(a)} data-alert={a.id}>
					<p class="mark" class:look={live(a)}>{standing(a)}</p>
					<h3>{a.title}</h3>
					<p class="meta">{a.summary}</p>
					<dl class="facts">
						<dt>Since</dt><dd>{moment(a.since)}</dd>
						<dt>Report</dt><dd>{a.state}</dd>
						{#if a.about.length}
							<dt>About</dt>
							<dd>
								<ul class="about">
									{#each a.about as r, n (n)}
										<li>
											{#if r.process_version}<a href={processLink(r.process_version)}>{r.process_version}</a>{/if}
											{#if r.run_id}run <a href={runLink(r.run_id)}>{r.run_id}</a>{/if}
											{#if r.step_id}, step {r.step_id}{/if}
										</li>
									{/each}
								</ul>
							</dd>
						{:else if a.kind === 'backup'}
							<dt>About</dt><dd><a href={backupLink}>the backup</a></dd>
						{/if}
					</dl>
					<details>
						<summary>What is needed, and the steps</summary>
						<ul>
							{#each a.needed as n, i (i)}<li>{n}</li>{/each}
						</ul>
						<ol>
							{#each a.steps as s, i (i)}<li>{s}</li>{/each}
						</ol>
						<p class="meta">{a.standing_still.join(' ')}</p>
					</details>
					<p class="id">{a.id}</p>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="empty">No alert was raised.</p>
	{/if}
</OperationPage>

<style>
	.about {
		list-style: none;
		padding: 0;
		margin: 0;
	}
</style>
