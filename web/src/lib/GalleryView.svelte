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

	<div class="shelf">
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
	</div>
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	/* The gallery as a shelf: one card per situation, side by side where there is room. */
	.shelf {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
		gap: var(--sp-250);
		margin-top: var(--sp-300);
		align-items: start;
	}
	.blueprint {
		position: relative;
		border: var(--bw-hairline) solid var(--border-subtle);
		border-radius: var(--r-2xl);
		padding: var(--sp-300) var(--sp-250) var(--sp-250);
		background: var(--bg-surface);
		box-shadow: var(--shadow-raised);
		overflow: hidden;
	}
	/* A band of the reproducible family across the top: every gallery process runs on rules. */
	.blueprint::before {
		content: '';
		position: absolute;
		inset: 0 0 auto;
		height: 4px;
		background: linear-gradient(to right, var(--family-reproducible), var(--accent-primary));
	}
	.blueprint h2 {
		margin-top: 0;
		color: var(--text-brand);
	}
	.process {
		border-top: var(--bw-hairline) solid var(--border-subtle);
		padding-top: var(--sp-200);
		margin-top: var(--sp-200);
	}
	.process h3 {
		margin-top: 0;
		font-family: var(--font-display);
		font-size: var(--fs-500);
		font-weight: var(--fw-bold);
		line-height: var(--lh-tight);
	}
	.steps {
		padding-inline-start: var(--sp-250);
		font-size: var(--fs-100);
	}
	.steps li + li {
		margin-top: var(--sp-050);
	}
	.refused {
		color: var(--text-subtle);
	}
	form {
		display: grid;
		gap: var(--sp-150);
		margin-top: var(--sp-200);
	}
	label {
		display: grid;
		gap: var(--sp-050);
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
	}
	input {
		font-size: var(--fs-100);
		font-weight: var(--fw-text);
		color: var(--text-primary);
	}
	form button {
		margin-top: var(--sp-100);
	}
	.message {
		background: var(--status-info-surface);
		color: var(--status-info-text);
		border: var(--bw-hairline) solid var(--status-info-border);
		border-radius: var(--r-lg);
		padding: var(--sp-150) var(--sp-200);
		max-width: 46rem;
	}
</style>
