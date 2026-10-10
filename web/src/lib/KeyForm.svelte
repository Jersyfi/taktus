<!--
	Asks for the reader's account key. The key is kept for this browser tab only (ADR-0063) and
	sent in the `Authorization` header, never in an address.
-->
<script lang="ts">
	import { keepKey } from './key';

	let { onKey, refused = false }: { onKey: (key: string) => void; refused?: boolean } = $props();
	let value = $state('');

	function submit(event: SubmitEvent) {
		event.preventDefault();
		keepKey(value);
		if (value.trim()) onKey(value.trim());
		value = '';
	}
</script>

<form onsubmit={submit}>
	{#if refused}
		<p role="alert">The surface did not accept the key. Give an account key that proves your identity.</p>
	{/if}
	<label>
		Account key
		<input type="password" autocomplete="off" bind:value required />
	</label>
	<button type="submit">Read</button>
	<p class="hint">Kept for this browser tab only, and sent to this instance and nowhere else.</p>
</form>

<style>
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: end;
		max-width: 36rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1 1 16rem;
	}
	input,
	button {
		font: inherit;
		padding: 0.4rem 0.6rem;
	}
	.hint {
		flex-basis: 100%;
		font-size: 0.85rem;
		opacity: 0.75;
		margin: 0;
	}
</style>
