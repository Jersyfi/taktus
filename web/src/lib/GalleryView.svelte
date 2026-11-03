<!--
	The gallery a person chooses a first process from (UC-10.4, ADR-0136 §5). Each gallery blueprint
	is shown with whom it is for and what it does; each of its processes with its steps in words, the
	autonomy level it starts at and why, and its choices, each prefilled with what the gallery
	offers. A process the gallery does not offer says why. Choosing sends the choices; the plan
	dialogue takes over from there. The page decides nothing and computes nothing.
-->
<script lang="ts">
	import type { GalleryBlueprint, GalleryProcess } from './types';

	let {
		blueprints,
		busy = false,
		message = null,
		onChoose
	}: {
		blueprints: GalleryBlueprint[];
		busy?: boolean;
		message?: string | null;
		onChoose: (blueprint: string, process: string, choices: Record<string, unknown>) => void;
	} = $props();

	// What the person typed, by blueprint, process and choice; what they did not touch is sent
	// as the gallery showed it.
	let typed: Record<string, string> = $state({});
	const key = (b: string, p: string, c: string) => `${b}/${p}/${c}`;

	function shown(value: unknown): string {
		return typeof value === 'string' ? value : JSON.stringify(value);
	}

	function choose(event: SubmitEvent, blueprint: string, process: GalleryProcess) {
		event.preventDefault();
		const choices: Record<string, unknown> = {};
		for (const choice of process.choices ?? []) {
			const given = typed[key(blueprint, process.id, choice.name)];
			if (given !== undefined) choices[choice.name] = given;
		}
		onChoose(blueprint, process.id, choices);
	}

	const methods: Record<string, string> = {
		rule: 'a fixed rule',
		statistics: 'statistics',
		ml: 'a trained model',
		neural: 'a neural network',
		llm: 'a language model',
		worker: 'a worker program',
		human: 'a person',
		wait: 'a pause'
	};
</script>

<section class="gallery" aria-labelledby="gallery-title">
	<p class="eyebrow">Gallery · a first process</p>
	<h1 id="gallery-title">Choose where to start.</h1>
	<p class="muted">
		Each one is a starting point you can change. Nothing runs until you have rehearsed it and said so; a
		rehearsal acts on nothing outside Taktus.
	</p>
	{#if message}<p class="message" aria-live="polite">{message}</p>{/if}

	{#if blueprints.length === 0}
		<p class="muted" data-empty>
			This instance's gallery is empty. A process can still be registered from its file, as the
			installation guide describes.
		</p>
	{/if}

	{#each blueprints as blueprint (blueprint.id)}
		<article class="blueprint" data-blueprint={blueprint.id}>
			<h2>{blueprint.title}</h2>
			<p class="muted">For {blueprint.for}. {blueprint.summary}</p>
			{#each blueprint.processes as process (process.id)}
				<div class="process" data-process={process.id}>
					<h3>{process.name}</h3>
					{#if process.refused}
						<p class="refused" data-refused>Not offered: {process.refused.join('; ')}</p>
					{:else}
						<p>{process.reason}.</p>
						<ol class="steps">
							{#each process.steps ?? [] as step (step.id)}
								<li>By {methods[step.method] ?? step.method}: {step.reason}.</li>
							{/each}
						</ol>
						<p class="muted">
							It starts at autonomy level {process.level}: {process.level_reason}.
						</p>
						<form onsubmit={(event) => choose(event, blueprint.id, process)}>
							{#each process.choices ?? [] as choice (choice.name)}
								<label>
									{choice.label}
									<input
										type="text"
										name={choice.name}
										value={typed[key(blueprint.id, process.id, choice.name)] ?? shown(choice.value)}
										oninput={(event) =>
											(typed[key(blueprint.id, process.id, choice.name)] = (event.currentTarget as HTMLInputElement).value)}
									/>
								</label>
							{/each}
							<button type="submit" class="primary" disabled={busy}>Make this my first process</button>
						</form>
					{/if}
				</div>
			{/each}
		</article>
	{/each}
</section>

<style>
	.eyebrow {
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-3);
		margin: 0 0 0.5rem;
	}
	.muted {
		color: var(--ink-2);
		font-size: 0.9rem;
	}
	.blueprint {
		border: 1px solid var(--line);
		border-radius: 18px;
		padding: 1rem 1.2rem;
		margin: 1rem 0;
		max-width: 52rem;
	}
	.process {
		border-top: 1px solid var(--line);
		padding-top: 0.75rem;
		margin-top: 0.75rem;
	}
	.steps {
		padding-left: 1.2rem;
	}
	.refused {
		color: var(--ink-3);
	}
	form {
		display: grid;
		gap: 0.6rem;
		max-width: 36rem;
	}
	label {
		display: grid;
		gap: 0.25rem;
	}
	input {
		font: inherit;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: var(--paper);
		color: var(--ink);
	}
	button {
		font: inherit;
		border: 1px solid var(--ink);
		border-radius: 10px;
		padding: 0.45rem 0.9rem;
		cursor: pointer;
		justify-self: start;
	}
	button.primary {
		background: var(--ink);
		color: var(--paper);
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.message {
		background: var(--paper-2);
		border-radius: 12px;
		padding: 0.7rem 0.9rem;
		max-width: 46rem;
	}
</style>
