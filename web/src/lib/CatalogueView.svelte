<!--
	What a person may ask Taktus for (UC-1.13, ADR-0159 §1). A list and a start button, nothing
	more: no ticket, no queue, no promised time (principle 1). Each entry says what it is for, what
	it needs, the level it runs at and the roles a person acts in; how to start it in the chat and
	from one's own agent; and the one start command every way issues. Starting opens the run.
-->
<script lang="ts">
	import { inputsOf, type Catalogue, type CatalogueEntry } from './views';

	let {
		catalogue,
		busy = false,
		message = null,
		onStart
	}: {
		catalogue: Catalogue;
		busy?: boolean;
		message?: string | null;
		onStart?: (process: string, inputs: Record<string, unknown>) => void;
	} = $props();

	let forms: Record<string, Record<string, string>> = $state({});

	function formOf(entry: CatalogueEntry): Record<string, string> {
		return forms[entry.process] ?? {};
	}

	function typed(entry: CatalogueEntry, name: string, value: string) {
		forms[entry.process] = { ...formOf(entry), [name]: value };
	}
</script>

<section class="catalogue" aria-labelledby="catalogue-title">
	<p class="eyebrow">What you may ask Taktus for</p>
	<h1 id="catalogue-title">{catalogue.summary}</h1>
	{#if message}<p role="alert">{message}</p>{/if}

	<ul class="entries">
		{#each catalogue.entries as entry (entry.process)}
			<li data-process={entry.process}>
				<h2>{entry.name}</h2>
				<p>{entry.text}</p>
				<form
					onsubmit={(event) => {
						event.preventDefault();
						onStart?.(entry.process, inputsOf(entry, formOf(entry)));
					}}
				>
					{#each entry.needs as input (input.name)}
						<label>
							<span>{input.name}{input.required ? '' : ' (optional)'} — {input.description}</span>
							<input
								name={input.name}
								required={input.required}
								value={formOf(entry)[input.name] ?? ''}
								oninput={(event) => typed(entry, input.name, event.currentTarget.value)}
							/>
						</label>
					{/each}
					{#if onStart}<button type="submit" disabled={busy}>Start {entry.name}</button>{/if}
				</form>
				<details>
					<summary>Other ways to start it</summary>
					<ul class="ways">
						{#if entry.start.chat}<li>In the chat, write <code>{entry.start.chat}</code></li>{/if}
						<li>
							From your own agent, call <code>{entry.start.agent.tool}</code>
							{entry.start.agent.held ? '' : `— it needs the right ${entry.start.agent.right}, which no role of yours holds`}
						</li>
						<li>Each issues the command <code>{entry.command.intent}</code> ({entry.command.recognised}).</li>
					</ul>
				</details>
			</li>
		{/each}
	</ul>
	<p class="muted">{catalogue.nothing_fits} <a href="#/gallery">The gallery</a></p>
</section>

<style>
	.entries {
		list-style: none;
		padding: 0;
		display: grid;
		gap: 0.8rem;
	}
	.entries > li {
		background: var(--bg-surface);
		border-radius: 18px;
		padding: 0.9rem 1rem;
	}
	h2 {
		font-family: var(--font-display);
		margin: 0 0 0.3rem;
	}
	form {
		display: grid;
		gap: 0.5rem;
		margin: 0.6rem 0;
	}
	label {
		display: grid;
		gap: 0.2rem;
		font-size: 0.86rem;
	}
	input {
		font: inherit;
		padding: 0.35rem 0.5rem;
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		background: var(--bg-canvas);
		color: var(--text-primary);
		max-width: 100%;
	}
	.ways,
	.muted {
		color: var(--text-secondary);
		font-size: 0.86rem;
	}
	code {
		overflow-wrap: anywhere;
	}
</style>
