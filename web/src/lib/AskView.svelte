<!--
	Ask Taktus (UC-1.14, ADR-0325): the reader's conversation with Taktus. Their turns and
	Taktus's answers in order; an act Taktus proposes as a card, read back, with "Yes, do it" and
	"No"; once settled, what came of it and links to what was made. Nothing is done before the
	reader's yes. The page computes nothing.
-->
<script lang="ts">
	import { actOf, linksOf, type ConversationView } from './conversation';

	let {
		view,
		busy = false,
		message = null,
		onSay,
		onAnswer
	}: {
		view: ConversationView;
		busy?: boolean;
		message?: string | null;
		onSay: (text: string) => void;
		onAnswer: (act: string, yes: boolean) => void;
	} = $props();

	let text = $state('');
	const thinking = $derived(view.thinking !== null);
	const closed = $derived(!view.available || busy || thinking);

	function submit() {
		const said = text.trim();
		if (!said || closed) return;
		onSay(said);
		text = '';
	}
</script>

<section class="ask" aria-labelledby="ask-title">
	<p class="eyebrow">Conversation · yours alone</p>
	<h1 id="ask-title">Ask Taktus</h1>
	<p class="muted">Say what you want done. Taktus proposes; nothing happens until you say yes.</p>

	{#if !view.available}
		<p class="message" data-unavailable>
			No conversation on this instance yet: the operator names its process in <code>TAKTUS_CONVERSATION_PROCESS</code>.
		</p>
	{/if}
	{#if message}<p class="message" role="alert">{message}</p>{/if}

	{#if view.turns.length === 0}
		<p class="muted" data-empty>
			For example: “Plan how we answer supplier invoices”, “Change daily-report: also mail the team”, “Start the
			monthly close”.
		</p>
	{:else}
		<ol class="turns" aria-label="Your conversation with Taktus">
			{#each view.turns as turn, i (i)}
				{@const act = actOf(view, turn)}
				<li class="turn {turn.speaker}" data-speaker={turn.speaker}>
					<span class="who">{turn.speaker === 'person' ? 'You' : 'Taktus'}</span>
					<p class="text">{turn.text}</p>
					{#if act}
						<article class="act" data-act={act.id} data-state={act.state} aria-label="Proposed: {act.act}">
							<p class="read-back">{act.read_back}</p>
							{#if act.state === 'waiting'}
								<div class="choices">
									<button type="button" disabled={busy} onclick={() => onAnswer(act.id, true)}>Yes, do it</button>
									<button type="button" class="quiet" disabled={busy} onclick={() => onAnswer(act.id, false)}>No</button>
								</div>
							{:else}
								<p class="state">{act.state === 'done' ? 'Done' : act.state === 'declined' ? 'Not done' : 'Refused'}</p>
								{#if linksOf(act).length}
									<ul class="links">
										{#each linksOf(act) as link (link.href)}<li><a href={link.href}>{link.label}</a></li>{/each}
									</ul>
								{/if}
							{/if}
						</article>
					{/if}
				</li>
			{/each}
		</ol>
	{/if}

	{#if thinking}<p class="muted" role="status" data-thinking>Taktus is answering…</p>{/if}

	<form
		class="say"
		onsubmit={(e) => {
			e.preventDefault();
			submit();
		}}
	>
		<label for="ask-text" class="hidden">What you want to say</label>
		<textarea
			id="ask-text"
			rows="2"
			maxlength="4000"
			placeholder="Ask or tell Taktus…"
			bind:value={text}
			disabled={!view.available}
			onkeydown={(e) => {
				if (e.key === 'Enter' && !e.shiftKey) {
					e.preventDefault();
					submit();
				}
			}}
		></textarea>
		<button type="submit" disabled={closed || !text.trim()}>Send</button>
	</form>
	<p class="muted hint">Enter sends · Shift+Enter starts a new line</p>
</section>

<style>
	.ask {
		display: grid;
		gap: var(--sp-150);
		max-width: 48rem;
	}
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.hint {
		font-size: var(--fs-075);
	}
	.message {
		background: var(--status-info-surface);
		color: var(--status-info-text);
		border: var(--bw-hairline) solid var(--status-info-border);
		border-radius: var(--r-lg);
		padding: var(--sp-150) var(--sp-200);
	}
	.turns {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: var(--sp-150);
	}
	.turn {
		display: grid;
		gap: var(--sp-050);
		max-width: min(40rem, 92%);
		border-radius: var(--r-xl);
		padding: var(--sp-150) var(--sp-200);
		border: var(--bw-hairline) solid var(--border-subtle);
	}
	.turn.person {
		justify-self: end;
		background: var(--bg-surface-sunken);
	}
	.turn.taktus {
		justify-self: start;
		background: var(--bg-surface);
	}
	.who {
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
	}
	.text {
		margin: 0;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
	.act {
		display: grid;
		gap: var(--sp-100);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-left-width: var(--sp-050);
		border-radius: var(--r-lg);
		padding: var(--sp-150);
	}
	.read-back {
		margin: 0;
		font-weight: var(--fw-semibold);
	}
	.choices {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-100);
	}
	.state {
		margin: 0;
		font-size: var(--fs-075);
		color: var(--text-subtle);
	}
	.links {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-100);
	}
	.say {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: var(--sp-100);
		align-items: end;
		position: sticky;
		bottom: 0;
		padding-block: var(--sp-100);
		background: var(--bg-canvas);
	}
	textarea {
		width: 100%;
		resize: vertical;
		font: inherit;
	}
	.hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
	@media (max-width: 40rem) {
		.turn {
			max-width: 100%;
		}
	}
</style>
