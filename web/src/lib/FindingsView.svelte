<!--
	This instance's findings and their review (UC-6.12, ADR-0118, ADR-0122). It opens with the
	surface's sentence. Each lack says what the rule over the release's list made of it, how often
	it was met and how long it held runs up, and the exact words it would leave in. At the level
	`review` a candidate waits for an answer — send, not now, or local for us. The answer is read
	back first and nothing is done; only the confirmation of what was read back acts (ADR-0008).
	The page sends what the reader chose and shows what the surface sent back; it decides nothing.
-->
<script lang="ts">
	import { duration } from './duration';
	import type { FindingsAnswer, ReviewChoice, ReviewReading } from './governance';
	import { runLink } from './links';

	let {
		answer,
		reading = null,
		message = null,
		busy = false,
		onAnswer,
		onConfirm
	}: {
		answer: FindingsAnswer;
		/** The answer read back, waiting for the reader's confirmation. */
		reading?: ReviewReading | null;
		/** What the surface said after the last confirmation. */
		message?: string | null;
		busy?: boolean;
		onAnswer: (lack: string, choice: ReviewChoice) => void;
		onConfirm: (confirmed: boolean) => void;
	} = $props();

	const KIND: Record<string, string> = {
		product: 'product candidate',
		configuration: 'local · configuration',
		own: 'local · own development',
		local_for_us: 'local for us'
	};
	const LEVEL: Record<string, string> = {
		off: 'Nothing leaves this instance: the operator’s level is off. A text can be sent by hand.',
		review: 'A candidate leaves only once a person said yes to the text below.',
		automatic: 'A candidate the rule raised leaves on its own.'
	};
</script>

<section class="findings" aria-labelledby="findings-title">
	<p class="eyebrow">Findings</p>
	<h1 id="findings-title">{answer.summary}</h1>
	<p class="level" data-level={answer.level}>Level <strong>{answer.level}</strong>. {LEVEL[answer.level]}</p>
	{#if message}<p class="message" role="status">{message}</p>{/if}

	<ul class="lacks">
		{#each answer.findings as f (f.lack.key)}
			<li class="lack" class:candidate={f.kind === 'product'} data-lack={f.lack.key} data-kind={f.kind}>
				<div class="head">
					<strong>{f.title}</strong>
					<span class="tag">{KIND[f.kind] ?? f.kind}</span>
				</div>
				<p>{f.said}</p>
				{#if f.classified.adapters.length}
					<p class="muted">Configure {f.classified.adapters.join(', ')}, which the release ships.</p>
				{/if}
				<p class="muted">
					Met {f.occurrences.length} {f.occurrences.length === 1 ? 'time' : 'times'}, runs held up {duration(f.waited_seconds)}:
					{#each f.occurrences as o, i (`${o.run}/${o.step}/${o.since}`)}
						{#if i > 0},&#32;{/if}<a href={runLink(o.run)}>{o.run}</a> · {o.step}
					{/each}
				</p>
				{#each f.withheld as w (`${w.kind}:${w.excerpt}`)}
					<p class="withheld">Withheld: it carries {w.kind.replaceAll('_', ' ')} <code>{w.excerpt}</code>.</p>
				{/each}
				<details>
					<summary>Exactly what would leave</summary>
					<pre>{f.text}</pre>
				</details>
				{#if f.in_review}
					{#if reading && reading.lack === f.lack.key}
						<div class="reading" aria-live="polite">
							<p>{reading.reading}</p>
							<div class="row">
								<button type="button" class="primary" disabled={busy} onclick={() => onConfirm(true)}>Yes, do it</button>
								<button type="button" disabled={busy} onclick={() => onConfirm(false)}>No, answer again</button>
							</div>
							<p class="muted">Nothing is done before you confirm.</p>
						</div>
					{:else}
						<div class="row" data-review={f.lack.key}>
							<button type="button" disabled={busy} onclick={() => onAnswer(f.lack.key, 'send')}>Send it</button>
							<button type="button" disabled={busy} onclick={() => onAnswer(f.lack.key, 'not')}>Not now</button>
							<button type="button" disabled={busy} onclick={() => onAnswer(f.lack.key, 'local')}>Local for us</button>
						</div>
					{/if}
				{/if}
			</li>
		{/each}
	</ul>

	<section class="text" aria-label="The findings as text">
		<h2>As text</h2>
		<ol>
			<li>{answer.summary}</li>
			{#each answer.findings as f (f.lack.key)}
				<li data-text="lack:{f.lack.key}">{f.said}{f.in_review ? ' It waits for a review.' : ''}</li>
			{/each}
		</ol>
	</section>
</section>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	h1 {
		max-width: 28ch;
	}
	.level,
	.muted {
		color: var(--ink-2);
		font-size: 0.88rem;
	}
	.message {
		background: var(--paper-2);
		border-radius: 12px;
		padding: 0.6rem 0.9rem;
		max-width: 46rem;
	}
	.lacks {
		list-style: none;
		padding: 0;
		display: grid;
		gap: 0.9rem;
		max-width: 52rem;
	}
	.lack {
		border-radius: 24px;
		padding: 1rem 1.2rem;
		background: var(--paper-2);
	}
	/* A candidate may leave: an outline on top of its tag, never colour alone. */
	.lack.candidate {
		box-shadow: inset 3px 0 0 var(--ink);
	}
	.lack p {
		margin: 0.3rem 0;
	}
	.head {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		align-items: baseline;
	}
	.tag {
		font-family: var(--mono);
		font-size: 0.7rem;
		border: 1px solid var(--ink-2);
		border-radius: 5px;
		padding: 0 0.35rem;
		white-space: nowrap;
	}
	.withheld {
		font-size: 0.85rem;
		color: var(--alert);
	}
	details pre {
		white-space: pre-wrap;
		font-family: var(--mono);
		font-size: 0.78rem;
		background: var(--paper);
		border-radius: 10px;
		padding: 0.75rem;
	}
	summary {
		cursor: pointer;
		font-size: 0.88rem;
	}
	.row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-top: 0.5rem;
	}
	button {
		font: inherit;
		border: 1px solid var(--line);
		background: var(--paper);
		color: var(--ink);
		border-radius: 10px;
		padding: 0.4rem 0.9rem;
		cursor: pointer;
	}
	button.primary {
		background: var(--ink);
		color: var(--paper);
		border-color: var(--ink);
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.reading {
		background: var(--paper);
		border-radius: 14px;
		padding: 0.8rem 1rem;
		margin-top: 0.5rem;
	}
</style>
