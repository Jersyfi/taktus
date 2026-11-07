<!--
	The automation coach (UC-13.3, ADR-0240): the reader's own hints, drawn from their own requests
	and shown to them alone; how many a week they want, the default stated where it is set; one
	switch that stops the coach reading their requests; and how many of their accepted hints
	lasted. Nobody else's hints or share appear here. The page computes nothing.
-->
<script lang="ts">
	import type { CoachState } from './workspace';

	let {
		coach,
		busy = false,
		message = null,
		onSet,
		onDismiss,
		onAccept
	}: {
		coach: CoachState;
		busy?: boolean;
		message?: string | null;
		onSet: (on: boolean, perWeek: number) => void;
		onDismiss: (hint: string) => void;
		onAccept: (hint: string, processVersion: string) => void;
	} = $props();

	let accepting: Record<string, string> = $state({});
</script>

<section class="coach" aria-labelledby="coach-title">
	<p class="eyebrow">Coach · yours alone</p>
	<h1 id="coach-title">What you could hand to Taktus</h1>
	<p class="muted">
		The coach notices requests you make again and again, from your own requests only, and tells you alone.
	</p>
	{#if message}<p class="message" aria-live="polite">{message}</p>{/if}

	<form
		class="settings"
		onsubmit={(e) => {
			e.preventDefault();
			const data = new FormData(e.currentTarget as HTMLFormElement);
			onSet(data.get('on') === 'on', Number(data.get('per_week')));
		}}
	>
		<label class="switch">
			<input type="checkbox" name="on" checked={coach.settings.on} />
			The coach is on — off, it reads none of your requests
		</label>
		<label>
			Hints a week (default {coach.settings.default_hints_per_week})
			<select name="per_week" value={String(coach.settings.hints_per_week)}>
				{#each [0, 1, 2, 3, 4, 5, 6, 7] as n (n)}<option value={String(n)}>{n === 0 ? 'none' : n}</option>{/each}
			</select>
		</label>
		<button type="submit" disabled={busy}>Save</button>
	</form>

	{#if !coach.settings.on}
		<p class="muted" data-off>The coach is off. Nothing you ask is read for hints.</p>
	{:else if coach.hints.length === 0}
		<p class="muted" data-empty>No hint for you right now.</p>
	{:else}
		<ul class="hints">
			{#each coach.hints as hint (hint.id)}
				<li data-hint={hint.id}>
					<p>{hint.says}</p>
					<form
						onsubmit={(e) => {
							e.preventDefault();
							onAccept(hint.id, accepting[hint.id] ?? '');
						}}
					>
						<label>
							The process that does it now (process@version)
							<input type="text" value={accepting[hint.id] ?? ''} oninput={(e) => (accepting[hint.id] = (e.currentTarget as HTMLInputElement).value)} />
						</label>
						<button type="submit" disabled={busy || !(accepting[hint.id] ?? '').trim()}>It is automated</button>
						<button type="button" class="quiet" disabled={busy} onclick={() => onDismiss(hint.id)}>Not for me</button>
					</form>
				</li>
			{/each}
		</ul>
	{/if}

	<p class="muted" data-share>
		Of your accepted hints that were checked, {coach.share.lasted} of {coach.share.checked} still run.
	</p>
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	form {
		display: grid;
		gap: var(--sp-150);
		max-width: 36rem;
		margin-top: var(--sp-200);
	}
	label {
		display: grid;
		gap: var(--sp-050);
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
	}
	.switch {
		display: flex;
		gap: var(--sp-100);
		align-items: center;
	}
	.hints {
		list-style: none;
		padding: 0;
		display: grid;
		gap: var(--sp-200);
	}
	.hints li {
		border: var(--bw-hairline) solid var(--border-subtle);
		border-radius: var(--r-xl);
		padding: var(--sp-200);
		background: var(--bg-surface);
	}
	.message {
		background: var(--status-info-surface);
		color: var(--status-info-text);
		border: var(--bw-hairline) solid var(--status-info-border);
		border-radius: var(--r-lg);
		padding: var(--sp-150) var(--sp-200);
	}
</style>
