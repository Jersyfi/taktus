<!--
	The processes Taktus proposes (UC-4.4, ADR-0270): work that recurs, each proposal saying the
	work it would take over, what it would cost and why now, in the order the surface hands over
	with the order's reason. Each is accepted or declined on its own. One drawn from the reader's
	own work is marked as theirs alone. The page computes nothing.
-->
<script lang="ts">
	import type { ProcessProposals } from './proposed';

	let {
		listed,
		busy = false,
		message = null,
		onAccept,
		onDecline
	}: {
		listed: ProcessProposals;
		busy?: boolean;
		message?: string | null;
		onAccept: (id: string) => void;
		onDecline: (id: string) => void;
	} = $props();
</script>

<section class="proposed" aria-labelledby="proposed-title">
	<p class="eyebrow">Proposed · work that recurs</p>
	<h1 id="proposed-title">What Taktus could take over</h1>
	<p class="muted" data-order>Ordered by {listed.order}, most often first.</p>
	{#if message}<p class="message" aria-live="polite">{message}</p>{/if}

	{#if listed.proposals.length === 0}
		<p class="muted" data-empty>Nothing to propose right now.</p>
	{:else}
		<ol class="proposals">
			{#each listed.proposals as proposal (proposal.id)}
				<li data-proposal={proposal.id}>
					<p class="takes">{proposal.takes_over}</p>
					<dl>
						<dt>Cost</dt>
						<dd>{proposal.cost}</dd>
						<dt>Why now</dt>
						<dd>{proposal.why_now}</dd>
						<dt>Order</dt>
						<dd>{proposal.order}</dd>
					</dl>
					{#if proposal.yours}<p class="muted" data-yours>Drawn from your own work: only you see it.</p>{/if}
					<div class="acts">
						<button type="button" disabled={busy} onclick={() => onAccept(proposal.id)}>Build it</button>
						<button type="button" class="quiet" disabled={busy} onclick={() => onDecline(proposal.id)}>Not now</button>
					</div>
				</li>
			{/each}
		</ol>
		<p class="muted">Building one prepares a proposal of a process; nothing runs for real before you commission it.</p>
	{/if}
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.proposals {
		list-style: none;
		padding: 0;
		display: grid;
		gap: var(--sp-200);
	}
	.proposals li {
		border: var(--bw-hairline) solid var(--border-subtle);
		border-radius: var(--r-xl);
		padding: var(--sp-200);
		background: var(--bg-surface);
	}
	.takes {
		font-weight: var(--fw-semibold);
	}
	dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: var(--sp-050) var(--sp-150);
		font-size: var(--fs-100);
	}
	dt {
		color: var(--text-subtle);
	}
	dd {
		margin: 0;
	}
	.acts {
		display: flex;
		gap: var(--sp-100);
		margin-top: var(--sp-150);
	}
	.message {
		background: var(--status-info-surface);
		color: var(--status-info-text);
		border: var(--bw-hairline) solid var(--status-info-border);
		border-radius: var(--r-lg);
		padding: var(--sp-150) var(--sp-200);
	}
</style>
