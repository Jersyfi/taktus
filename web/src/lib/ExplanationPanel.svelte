<!--
	Why each step of a run was done the way it was (UC-6.5, ADR-0243): per step a "Why?" that
	reads `GET /levels/runs/{run}/steps/{step}/explanation` and shows its lines — what was done,
	by which method and why, what was rejected, what it consumed and what came out, at the depth
	and in the language of the reader's role. Every number in it is a number of the records; the
	page adds none.
-->
<script lang="ts">
	import { read } from './api';
	import type { StepExplanation } from './figures';
	import type { RunLevel } from './types';

	let { level, base, onRefused }: { level: RunLevel; base: URL; onRefused: () => void } = $props();

	let explained = $state<Record<string, StepExplanation>>({});
	let problems = $state<Record<string, string>>({});
	let busy = $state<string | null>(null);

	async function why(step: string) {
		busy = step;
		const run = level.run.id;
		const answer = await read<StepExplanation>(
			base,
			`levels/runs/${encodeURIComponent(run)}/steps/${encodeURIComponent(step)}/explanation`
		);
		busy = null;
		if (answer.ok) explained = { ...explained, [step]: answer.body };
		else if (answer.problem.status === 401) onRefused();
		else problems = { ...problems, [step]: answer.problem.detail || answer.problem.title };
	}
</script>

<section class="why" aria-labelledby="why-title">
	<h2 id="why-title">Why each step was done this way</h2>
	<ul>
		{#each level.steps as step (step.id)}
			<li data-why={step.id}>
				<div class="head">
					<code>{step.id}</code>
					<button type="button" class="quiet" disabled={busy === step.id} aria-expanded={!!explained[step.id]} onclick={() => why(step.id)}>Why?</button>
				</div>
				{#if explained[step.id]}
					<ol class="lines">
						{#each explained[step.id]!.lines as line, i (i)}<li>{line}</li>{/each}
					</ol>
				{:else if problems[step.id]}
					<p class="muted" role="alert">{problems[step.id]}</p>
				{/if}
			</li>
		{/each}
	</ul>
</section>

<style>
	ul {
		list-style: none;
		padding: 0;
		max-width: 48rem;
	}
	ul > li {
		padding: var(--sp-100) 0;
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--sp-200);
	}
	.lines {
		margin: var(--sp-100) 0 0;
		color: var(--text-secondary);
	}
	.muted {
		color: var(--text-secondary);
	}
</style>
