<!--
	Each process's level and its correction rates: `GET /autonomy` (ADR-0122), read on opening.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import AutonomyView from '../../lib/AutonomyView.svelte';
	import type { AutonomyAnswer } from '../../lib/governance';
	import KeyForm from '../../lib/KeyForm.svelte';
	import { currentKey } from '../../lib/key';

	let key = $state(currentKey());
	let refused = $state(false);
	let answer: AutonomyAnswer | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!key) return;
		void read<AutonomyAnswer>(surface(location.href), 'autonomy', key).then((found) => {
			if (found.ok) answer = found.body;
			else if (found.problem.status === 401) {
				refused = true;
				key = null;
			} else problem = found.problem.detail || found.problem.title;
		});
	});
</script>

{#if !key}
	<KeyForm {refused} onKey={(k) => (key = k)} />
{:else if answer}
	<AutonomyView {answer} />
{:else if problem}
	<p role="alert">{problem}</p>
{:else}
	<p class="status">Reading the levels…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
