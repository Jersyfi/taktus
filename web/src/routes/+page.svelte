<!--
	The overview of UC-6.10, live (ADR-0067): it follows the tenant's stream of changes and reads
	the overview again whenever one arrives, as every level does (ADR-0063). It is where the web
	app starts, and where every other level leads back to.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import { surface } from '../lib/api';
	import SignInForm from '../lib/SignInForm.svelte';
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

	let signedIn = $state(true);
	let connected = $state(false);
	let level: OverviewLevel | null = $state(null);
	let stop: AbortController | null = null;

	$effect(() => {
		if (!signedIn) return;
		stop?.abort();
		const controller = new AbortController();
		stop = controller;
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
			onConnected: (open) => (connected = open)
		});
	});
	onDestroy(() => stop?.abort());

	// What governs the work (ADR-0122): read once on opening, one line per kind.
	let governs: Line[] = $state([]);
	$effect(() => {
		if (!signedIn) return;
		void governanceLines(surface(location.href), currentAdministrationKey()).then((found) => (governs = found));
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if level}
	<p class="status" aria-live="polite">{connected ? 'Live.' : 'Reconnecting…'}</p>
	<OperationSection />
	<OverviewView {level} motionAllowed={motion.allowed} />
{:else}
	<p class="status">Reading the overview…</p>
{/if}
{#if signedIn && governs.length}<GovernanceLines lines={governs} />{/if}

<!-- The reports that wait for an answer, each leading to its page (DEC-0218, ADR-0120). -->
{#if signedIn}
	<OpenReports />
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
