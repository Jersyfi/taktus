<!--
	Signs the reader in (ADR-0119). The account key is sent once, in the `Authorization` header,
	in exchange for a session cookie the page cannot read; then the form forgets it. The key is
	never kept and never put in an address.
-->
<script lang="ts">
	import { surface } from './api';
	import { signIn } from './session';

	let { onSignedIn }: { onSignedIn: () => void } = $props();
	let value = $state('');
	let refused = $state(false);
	let busy = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		const key = value.trim();
		value = '';
		if (!key) return;
		busy = true;
		const answer = await signIn(surface(location.href), key);
		busy = false;
		refused = !answer.ok;
		if (answer.ok) onSignedIn();
	}
</script>

<form onsubmit={submit}>
	{#if refused}
		<p role="alert">The instance did not accept the key. Give an account key that proves your identity.</p>
	{/if}
	<label>
		Account key
		<input type="password" autocomplete="off" bind:value required />
	</label>
	<button type="submit" disabled={busy}>Sign in</button>
	<p class="hint">
		Sent once to this instance and nowhere else, then forgotten. You stay signed in on this browser until you sign out
		or the sign-in expires.
	</p>
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
