<!--
	Today: the overview of UC-6.10, live (ADR-0067), ordered by what waits for the reader
	(ADR-0178 §3). It follows the tenant's stream of changes and reads the overview again whenever
	one arrives, as every level does (ADR-0063). Under the sentence, how many changes arrived since
	the page opened; then what waits for the reader; then what runs; then what keeps the operation
	running and what governs the work; then the text equivalent. It is where the web app starts,
	and where every other level leads back to.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { surface } from '../lib/api';
	import { frame } from '../lib/frame.svelte';
	import SignInForm from '../lib/SignInForm.svelte';
	import { galleryLink } from '../lib/links';
	import { followLevel } from '../lib/live';
	import { motion } from '../lib/motion.svelte';
	import OverviewView from '../lib/OverviewView.svelte';
	import OpenReports from '../lib/OpenReports.svelte';
	// What keeps the operation running (ADR-0121): a section of its own.
	import OperationSection from '../lib/OperationSection.svelte';
	import type { OverviewLevel } from '../lib/types';
	// What governs the work (ADR-0122): a section of its own.
	import { currentAdministrationKey, governanceLines, type Line } from '../lib/governance';
	import GovernanceLines from '../lib/GovernanceLines.svelte';
	import { changesLine, nothingWaits } from '../lib/today';

	let signedIn = $state(true);
	let level: OverviewLevel | null = $state(null);
	let stop: AbortController | null = null;

	$effect(() => {
		if (!signedIn) return;
		stop?.abort();
		const controller = new AbortController();
		stop = controller;
		frame.follow();
		void followLevel<OverviewLevel>({
			base: surface(location.href),
			path: 'levels/overview',
			scope: {},
			signal: controller.signal,
			onLevel: (found) => (level = found),
			onAbsent: () => (level = null),
			onRefused: () => {
				signedIn = false;
			},
			onConnected: (open) => frame.connected(open),
			onChange: () => frame.changed()
		});
	});
	onDestroy(() => {
		stop?.abort();
		frame.leave();
	});

	// What governs the work (ADR-0122): read once on opening, one line per kind.
	let governs: Line[] = $state([]);
	$effect(() => {
		if (!signedIn) return;
		void governanceLines(surface(location.href), currentAdministrationKey()).then((found) => (governs = found));
	});
	const forYou = $derived(governs.filter((l) => l.waiting));
	const rest = $derived(governs.filter((l) => !l.waiting));
	const empty = $derived.by(() => {
		const shown = level as OverviewLevel | null;
		return shown !== null && shown.areas.every((area) => area.processes.length === 0);
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if level}
	<OverviewView {level} motionAllowed={motion.allowed}>
		{#snippet lead()}
			<p class="changes" aria-live="polite" data-changes={frame.changes}>
				<span class="state" class:on={frame.live}>{frame.live ? 'Live' : 'Reconnecting…'}</span>
				<span>{changesLine(frame.changes)}</span>
			</p>
		{/snippet}
		{#snippet between()}
			{#if empty}
				<!-- A tenant with no process yet starts from the gallery (UC-10.4, ADR-0136 §5). -->
				<section class="first" data-first-process aria-labelledby="first-title">
					<h2 id="first-title">Your first process</h2>
					<ol class="path">
						<li><strong>Choose</strong> a process from the gallery, for a family, a club or a small business.</li>
						<li><strong>Rehearse</strong> it: it runs, and acts on nothing outside Taktus.</li>
						<li><strong>Commission</strong> it once the rehearsal shows what it does.</li>
					</ol>
					<p>
						Nothing runs here yet. <a class="go" href={galleryLink()}>Choose a first process from the gallery</a>, rehearse it,
						and see what it does before it does anything for real.
					</p>
				</section>
			{/if}
			<section class="for-you" aria-label="For you">
				{#if forYou.length}
					<GovernanceLines lines={forYou} title="For you" />
				{:else if nothingWaits(governs.map((l) => l.kind))}
					<h2>For you</h2>
					<p class="calm" data-for-you="none">{nothingWaits(governs.map((l) => l.kind))}</p>
				{/if}
				<!-- The reports that wait for an answer, each leading to its page (DEC-0218, ADR-0120). -->
				<OpenReports />
			</section>
		{/snippet}
		{#snippet after()}
			<OperationSection />
			{#if rest.length}<GovernanceLines lines={rest} />{/if}
		{/snippet}
	</OverviewView>
{:else}
	<p class="reading">Reading the overview…</p>
{/if}

<style>
	.changes {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--sp-150);
		margin: 0;
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.state {
		display: inline-flex;
		align-items: center;
		gap: var(--sp-050);
		padding: var(--sp-025) var(--sp-150);
		border-radius: var(--r-full);
		background: var(--status-neutral-surface);
		color: var(--status-neutral-text);
		font-weight: var(--fw-semibold);
		font-size: var(--fs-075);
	}
	.state::before {
		content: '';
		width: 8px;
		height: 8px;
		border-radius: var(--r-full);
		border: var(--bw-thick) solid currentColor;
	}
	.state.on {
		background: var(--status-success-surface);
		color: var(--status-success-text);
	}
	.state.on::before {
		background: currentColor;
	}
	.for-you {
		margin-top: var(--sp-300);
	}
	.calm {
		font-size: var(--fs-300);
		margin: 0;
	}
	.first {
		margin: var(--sp-300) 0 var(--sp-400);
		padding: var(--sp-300);
		border-radius: var(--r-2xl);
		background:
			radial-gradient(90% 120% at 100% 0%, var(--accent-primary-subtle), transparent 70%),
			var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		box-shadow: var(--shadow-raised);
	}
	.first h2 {
		margin-top: 0;
	}
	.path {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
		gap: var(--sp-200);
		padding: 0;
		margin: 0 0 var(--sp-200);
		list-style: none;
		counter-reset: step;
	}
	.path li {
		counter-increment: step;
		color: var(--text-secondary);
	}
	.path li::before {
		content: counter(step);
		display: grid;
		place-items: center;
		width: var(--sp-400);
		height: var(--sp-400);
		margin-bottom: var(--sp-100);
		border-radius: var(--r-full);
		background: var(--accent-primary);
		color: var(--text-inverse);
		font-weight: var(--fw-bold);
	}
	.path strong {
		color: var(--text-primary);
	}
	.go {
		display: inline-block;
		font-weight: var(--fw-semibold);
	}
	.reading {
		color: var(--text-secondary);
	}
</style>
