<!--
	The process level of one process version, live (UC-6.10, ADR-0064). Read at once, and again on
	every change of the frame's stream that concerns the process (ADR-0323 §2). Without a version
	in the address, the active version is drawn.
-->
<script lang="ts">
	import { page } from '$app/state';
	import { failed, surface } from '../../../../lib/api';
	import EmptyState from '../../../../lib/EmptyState.svelte';
	import ErrorState from '../../../../lib/ErrorState.svelte';
	import { frame } from '../../../../lib/frame.svelte';
	import { ofProcess, watchLevel } from '../../../../lib/live';
	import { motion } from '../../../../lib/motion.svelte';
	import ProcessView from '../../../../lib/ProcessView.svelte';
	import SignInForm from '../../../../lib/SignInForm.svelte';
	import Skeleton from '../../../../lib/Skeleton.svelte';
	import Unavailable from '../../../../lib/Unavailable.svelte';
	import type { Problem, ProcessLevel } from '../../../../lib/types';

	let signedIn = $state(true);
	let absent = $state(false);
	let level: ProcessLevel | null = $state(null);
	let problem: Problem | null = $state(null);
	let again: (() => Promise<void>) | null = null;

	const processId = $derived(page.params.id ?? '');
	const version = $derived(page.params.version ?? '');

	$effect(() => {
		if (!signedIn || !processId) return;
		const controller = new AbortController();
		level = null;
		problem = null;
		absent = false;
		const path = `levels/processes/${encodeURIComponent(processId)}${version ? `?version=${encodeURIComponent(version)}` : ''}`;
		again = watchLevel<ProcessLevel>({
			base: surface(location.href),
			path,
			concerns: ofProcess(processId),
			hub: frame,
			signal: controller.signal,
			onLevel: (found) => {
				level = found;
				absent = false;
				problem = null;
			},
			onAbsent: () => {
				absent = true;
				level = null;
			},
			onRefused: () => (signedIn = false),
			onFailed: (found) => (problem = found)
		}).again;
		return () => controller.abort();
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if absent}
	<EmptyState title="No process {processId}{version ? `@${version}` : ''} you may see." />
{:else if level}
	<ProcessView {level} motionAllowed={motion.allowed} />
{:else if problem && failed(problem)}
	<ErrorState what="Process {processId}" {problem} onRetry={() => void again?.()} />
{:else if problem}
	<Unavailable eyebrow="Process" problem={problem.detail || problem.title} />
{:else}
	<Skeleton label="Reading process {processId}…" />
{/if}
