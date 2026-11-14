<!--
	Every process the reader may see (ADR-0321 §2): the overview level of UC-6.10 with its sentence,
	each process drawn as its cells, with its level, how many of its runs work and wait, and its
	exactness statement folded (UC-6.9). Read at once and again on every change of the frame's
	stream (ADR-0323 §2).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { failed, read, surface } from '../../lib/api';
	import { display } from '../../lib/display.svelte';
	import DisplaySwitch from '../../lib/DisplaySwitch.svelte';
	import EmptyState from '../../lib/EmptyState.svelte';
	import ErrorState from '../../lib/ErrorState.svelte';
	import { frame } from '../../lib/frame.svelte';
	import { galleryLink } from '../../lib/links';
	import { Rereader } from '../../lib/live';
	import { motion } from '../../lib/motion.svelte';
	import OverviewView from '../../lib/OverviewView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import Skeleton from '../../lib/Skeleton.svelte';
	import type { OverviewLevel, Problem } from '../../lib/types';

	const PAGE = 'processes';
	let signedIn = $state(true);
	let level = $state<OverviewLevel | null>(null);
	let problem = $state<Problem | null>(null);

	const rereader = new Rereader(async () => {
		const found = await read<OverviewLevel>(surface(location.href), 'levels/overview');
		if (found.ok) {
			level = found.body;
			problem = null;
		} else if (found.problem.status === 401) signedIn = false;
		else problem = found.problem;
	});

	onMount(() => {
		void rereader.request();
		return frame.subscribe(() => void rereader.request());
	});

	const empty = $derived(level !== null && level.areas.every((a) => a.processes.length === 0));
</script>

{#if !signedIn}
	<SignInForm
		onSignedIn={() => {
			signedIn = true;
			void rereader.request();
		}}
	/>
{:else if level}
	<div class="tools"><DisplaySwitch page={PAGE} /></div>
	{#if empty}
		<p class="eyebrow">Processes</p>
		<h1>No process yet.</h1>
		<EmptyState title="No process you may see.">
			<p><a href={galleryLink()}>Choose a first process from the gallery</a>, rehearse it, then commission it.</p>
		</EmptyState>
	{:else}
		<OverviewView {level} motionAllowed={motion.allowed} mode={display.of(PAGE)} />
	{/if}
{:else if problem && failed(problem)}
	<ErrorState what="The processes" {problem} onRetry={() => void rereader.request()} />
{:else if problem}
	<p role="alert">{problem.detail || problem.title}</p>
{:else}
	<Skeleton label="Reading the processes…" />
{/if}

<style>
	.tools {
		display: flex;
		justify-content: flex-end;
	}
</style>
