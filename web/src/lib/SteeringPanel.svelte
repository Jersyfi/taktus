<!--
	A message to a running worker step (ADR-0156 §7). Each running worker step offers a field; the
	text is read back before it is sent, and nothing is sent before the reader confirms it
	(ADR-0008). A message never widens what the step may do or spend. No person is named here
	(principle 14).
-->
<script lang="ts">
	import { readMessage, steerable } from './steering';
	import type { RunLevel } from './types';

	let {
		level,
		said = null,
		busy = false,
		onSend
	}: {
		level: RunLevel;
		/** What the surface said after the last message. */
		said?: string | null;
		busy?: boolean;
		onSend: (step: string, text: string) => void;
	} = $props();

	const steps = $derived(steerable(level));
	let written: Record<string, string> = $state({});
	let reading: Record<string, string | null> = $state({});

	function readBack(step: string, event: SubmitEvent) {
		event.preventDefault();
		reading[step] = readMessage(written[step] ?? '');
	}

	function confirm(step: string) {
		const text = reading[step];
		if (!text) return;
		onSend(step, text);
		reading[step] = null;
		written[step] = '';
	}
</script>

{#if steps.length || said}
	<section class="steering" aria-labelledby="steering-title">
		<h2 id="steering-title">Send a message</h2>
		{#if said}
			<p class="said" aria-live="polite">{said}</p>
		{/if}
		{#each steps as step (step.id)}
			<form class="card" data-steer={step.id} onsubmit={(e) => readBack(step.id, e)}>
				<label for={`steer-${step.id}`}>A message to {step.id}, received at its worker's next boundary</label>
				<textarea id={`steer-${step.id}`} maxlength="8000" bind:value={written[step.id]}></textarea>
				<button type="submit" disabled={busy}>Read back</button>
				{#if reading[step.id]}
					<p class="reading" data-reading={step.id}>
						This sends {step.id} the message “{reading[step.id]}”. It changes nothing the step may do or spend.
					</p>
					<button type="button" disabled={busy} onclick={() => confirm(step.id)}>Send</button>
				{/if}
			</form>
		{/each}
	</section>
{/if}

<style>
	.steering {
		display: grid;
		gap: 0.75rem;
	}
	.card {
		display: grid;
		gap: 0.5rem;
	}
	textarea {
		min-height: 4rem;
		width: 100%;
	}
</style>
