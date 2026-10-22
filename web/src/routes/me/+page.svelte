<!--
	The reader's own page: `GET /decisions/response-times`, which the surface computes for its
	reader alone (ADR-0015). Read once on opening.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import SignInForm from '../../lib/SignInForm.svelte';
	import type { ResponseTimes } from '../../lib/types';
	import YoursView from '../../lib/YoursView.svelte';

	let signedIn = $state(true);
	let times: ResponseTimes | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<ResponseTimes>(surface(location.href), 'decisions/response-times').then((answer) => {
			if (answer.ok) times = answer.body;
			else if (answer.problem.status === 401) {
				signedIn = false;
			}
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if times}
	<YoursView {times} />
{:else}
	<p class="status">Reading your own times…</p>
{/if}

<style>
	.status {
		color: var(--muted);
		font-size: 0.9rem;
	}
</style>
