<!--
	One read of the surface, drawn when it answers: the sign-in where the reader has none, the
	surface's problem where it refuses, and a line while it reads. The pages of ADR-0147 are each
	one such read; `path` changing reads again.
-->
<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { read, surface } from './api';
	import SignInForm from './SignInForm.svelte';

	let { path, reading, children }: { path: string; reading: string; children: Snippet<[T]> } = $props();

	let signedIn = $state(true);
	let answer: T | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		answer = null;
		problem = null;
		void read<T>(surface(location.href), path).then((found) => {
			if (found.ok) answer = found.body;
			else if (found.problem.status === 401) signedIn = false;
			else problem = found.problem.detail || found.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if answer}
	{@render children(answer)}
{:else if problem}
	<p role="alert">{problem}</p>
{:else}
	<p class="status">{reading}</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
