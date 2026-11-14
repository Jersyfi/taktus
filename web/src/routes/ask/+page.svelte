<!--
	Ask Taktus (UC-1.14, ADR-0325): reads `GET /conversation`, says something with
	`POST /conversation`, and answers an act with `POST /conversation/acts/{act}`. While a run
	forms Taktus's answer, the page asks for the conversation again, less often the longer it
	waits.
-->
<script lang="ts">
	import { read, send, surface } from '../../lib/api';
	import AskView from '../../lib/AskView.svelte';
	import SignInForm from '../../lib/SignInForm.svelte';
	import { nextAsk, waitingForAnswer, type ConversationView } from '../../lib/conversation';

	let signedIn = $state(true);
	let view: ConversationView | null = $state(null);
	let message: string | null = $state(null);
	let busy = $state(false);
	let asked = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;
	const base = () => surface(location.href);

	async function refresh() {
		const done = await read<ConversationView>(base(), 'conversation');
		if (done.ok) {
			view = done.body;
			later();
		} else if (done.problem.status === 401) signedIn = false;
		else message = done.problem.detail || done.problem.title;
	}

	function later() {
		clearTimeout(timer);
		if (!waitingForAnswer(view)) {
			asked = 0;
			return;
		}
		timer = setTimeout(() => void refresh(), nextAsk(asked++));
	}

	async function acted(path: string, body: unknown) {
		busy = true;
		message = null;
		const done = await send<unknown>(base(), path, body);
		busy = false;
		if (!done.ok) {
			if (done.problem.status === 401) signedIn = false;
			else message = done.problem.detail || done.problem.title;
		}
		await refresh();
	}

	$effect(() => {
		if (!signedIn) return;
		void refresh();
		return () => clearTimeout(timer);
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if view}
	<AskView
		{view}
		{busy}
		{message}
		onSay={(text) => void acted('conversation', { text })}
		onAnswer={(act, yes) => void acted(`conversation/acts/${encodeURIComponent(act)}`, { yes })}
	/>
{:else}
	<p class="status">{message ?? 'Reading your conversation…'}</p>
{/if}

<style>
	.status {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
</style>
