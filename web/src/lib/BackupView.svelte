<!--
	The backup (ADR-0106 §3, §5): the last success the backup program recorded, the newest failed
	run, and by when the next success is due. A backup is known only from what it recorded; a
	recorded success does not say that it restores, which the restore drill shows.
-->
<script lang="ts">
	import { backupAge, backupSentence, moment, type BackupRecord } from './operation';
	import OperationPage from './OperationPage.svelte';

	let { backup, now = new Date() }: { backup: BackupRecord; now?: Date } = $props();
	const listed = $derived(backup.listed ?? []);

	const look = $derived(backup.standing === 'failing' || backup.standing === 'missing');
	const sentence = $derived(backupSentence(backup));
	const STANDING: Record<string, string> = {
		ok: 'Succeeded',
		failing: 'Failing',
		missing: 'Missing',
		not_recorded: 'Not recorded'
	};
	const lines = $derived(
		[
			backup.last_ok ? `Last success: ${backup.last_ok.name} at ${moment(backup.last_ok.at)}.` : 'No success recorded.',
			backup.newest_failed
				? `Newest failure: ${backup.newest_failed.name} at ${moment(backup.newest_failed.at)}, step ${backup.newest_failed.reason ?? 'unknown'}.`
				: '',
			backup.watched
				? `Next due by ${moment(backup.next_due)}, every ${backup.expected_hours} hours.`
				: 'A missing backup is not watched: TAKTUS_BACKUP_EXPECTED_HOURS is not set.'
		].filter(Boolean)
	);
</script>

<OperationPage eyebrow="Backup" {sentence} {lines}>
	<div class="record backup" class:look data-standing={backup.standing}>
		<p class="mark" class:look class:unknown={backup.standing === 'not_recorded'}>{STANDING[backup.standing]}</p>
		<dl class="facts">
			<dt>Last success</dt>
			<dd>{#if backup.last_ok}{backup.last_ok.name}, {moment(backup.last_ok.at)}{:else}none recorded{/if}</dd>
			{#if backup.newest_failed}
				<dt>Newest failure</dt>
				<dd>
					{backup.newest_failed.name}, {moment(backup.newest_failed.at)}, at the step
					<code>{backup.newest_failed.reason}</code>
				</dd>
				<dt>Failed since</dt><dd>{backup.failed_count} {backup.failed_count === 1 ? 'run' : 'runs'}</dd>
			{/if}
			<dt>Next due by</dt>
			<dd>
				{#if backup.watched}{moment(backup.next_due)}{:else}not watched: <code>TAKTUS_BACKUP_EXPECTED_HOURS</code> is not set{/if}
			</dd>
			{#if backup.expected_hours}<dt>Interval</dt><dd>{backup.expected_hours} hours</dd>{/if}
		</dl>
		<h2>The newest backups</h2>
		<ol class="listed" data-act="backup.list">
			{#each listed as run (run.name)}
				<li data-outcome={run.outcome}>
					<code>{run.name}</code>, {moment(run.at)}, {backupAge(run.at, now)}:
					{#if run.outcome === 'ok'}succeeded{:else}failed at the step <code>{run.reason ?? 'unknown'}</code>{/if}
				</li>
			{:else}
				<li>No backup recorded.</li>
			{/each}
		</ol>
		<p class="hint">Restoring one is a person's act, by the guide <em>Restoring</em>; Taktus offers none.</p>
		{#if backup.alert}
			<details open>
				<summary>{backup.alert.title}</summary>
				<ul>
					{#each backup.alert.needed as n, i (i)}<li>{n}</li>{/each}
				</ul>
				<ol>
					{#each backup.alert.steps as s, i (i)}<li>{s}</li>{/each}
				</ol>
			</details>
		{/if}
	</div>
</OperationPage>

<style>
	.hint {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.listed {
		padding-left: 1.2rem;
	}
	.backup {
		max-width: 44rem;
	}
	code {
		font-family: var(--font-mono);
		font-size: var(--fs-090);
	}
</style>
