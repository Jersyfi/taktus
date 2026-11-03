<!--
	Signs the reader in (ADR-0119). The account key is sent once, in the `Authorization` header,
	in exchange for a session cookie the page cannot read; then the form forgets it. The key is
	never kept and never put in an address.
-->
<script lang="ts">
	import { surface } from './api';
	import Mark from './Mark.svelte';
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

<section class="door" aria-labelledby="sign-in-title">
	<Mark size={56} />
	<h1 id="sign-in-title">Sign in to Taktus</h1>
	<form onsubmit={submit}>
		{#if refused}
			<p class="refused" role="alert">The instance did not accept the key. Give an account key that proves your identity.</p>
		{/if}
		<label>
			Account key
			<input type="password" autocomplete="off" bind:value required />
		</label>
		<button type="submit" class="primary" disabled={busy}>Sign in</button>
		<p class="hint">
			Sent once to this instance and nowhere else, then forgotten. You stay signed in on this browser until you sign out
			or the sign-in expires.
		</p>
	</form>
</section>

<style>
	.door {
		display: grid;
		justify-items: start;
		gap: var(--sp-200);
		max-width: 30rem;
		margin: var(--sp-800) auto;
		padding: var(--sp-400);
		border-radius: var(--r-2xl);
		background:
			radial-gradient(90% 80% at 100% 0%, var(--accent-primary-subtle), transparent 70%),
			var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		box-shadow: var(--shadow-overlay);
	}
	h1 {
		font-size: var(--fs-600);
		margin: 0;
	}
	form {
		display: grid;
		gap: var(--sp-150);
		width: 100%;
	}
	label {
		display: grid;
		gap: var(--sp-050);
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
	}
	input {
		font-size: var(--fs-200);
		color: var(--text-primary);
	}
	.hint {
		font-size: var(--fs-075);
		color: var(--text-secondary);
		margin: 0;
	}
	.refused {
		margin: 0;
		color: var(--text-danger);
	}
</style>
