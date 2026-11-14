<!--
	One read of the surface, drawn when it answers: the sign-in where the reader has none, the
	surface's refusal in its own words, a failure as a failure with a way to read again, and a
	skeleton while it reads (ADR-0322 §5). The pages of ADR-0147 are each one such read; `path`
	changing reads again.
-->
<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { failed, read, surface } from './api';
	import ErrorState from './ErrorState.svelte';
	import SignInForm from './SignInForm.svelte';
	import Skeleton from './Skeleton.svelte';
	import type { Problem } from './types';

	let { path, reading, children }: { path: string; reading: string; children: Snippet<[T]> } = $props();

	let signedIn = $state(true);
	let answer: T | null = $state(null);
	let problem = $state<Problem | null>(null);
	let attempt = $state(0);

	$effect(() => {
		if (!signedIn) return;
		void attempt;
		answer = null;
		problem = null;
		void read<T>(surface(location.href), path).then((found) => {
			if (found.ok) answer = found.body;
			else if (found.problem.status === 401) signedIn = false;
			else problem = found.problem;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if answer}
	{@render children(answer)}
{:else if problem && failed(problem)}
	<ErrorState what="This page" {problem} onRetry={() => (attempt += 1)} />
{:else if problem}
	<p role="alert">{problem.detail || problem.title}</p>
{:else}
	<Skeleton label={reading} />
{/if}
