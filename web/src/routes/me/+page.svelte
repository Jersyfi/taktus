<!--
	The reader's own page: `GET /decisions/response-times`, which the surface computes for its
	reader alone (ADR-0015). Read once on opening.
-->
<script lang="ts">
	import { read, surface } from '../../lib/api';
	import KeyForm from '../../lib/KeyForm.svelte';
	import { currentKey } from '../../lib/key';
	import type { ResponseTimes } from '../../lib/types';
	import YoursView from '../../lib/YoursView.svelte';

	let key = $state(currentKey());
	let refused = $state(false);
	let times: ResponseTimes | null = $state(null);

	$effect(() => {
		if (!key) return;
		void read<ResponseTimes>(surface(location.href), 'decisions/response-times', key).then((answer) => {
			if (answer.ok) times = answer.body;
			else if (answer.problem.status === 401) {
				refused = true;
				key = null;
			}
		});
	});
</script>

{#if !key}
	<KeyForm {refused} onKey={(k) => (key = k)} />
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
