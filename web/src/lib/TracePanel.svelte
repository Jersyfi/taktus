<!--
	The trace inside a worker's step, live (UC-6.14, ADR-0135). Every event the worker reported is
	a line on a thread, in the order it came: what the worker planned, said, called or refused,
	chose, used and produced, and how it ended. Each kind of event has a form of its own, never
	only a colour. Only the newest line of a step in flight moves, and only where motion is
	allowed: motion means work happening now (UC-6.10). Every secret value is masked by the
	surface before it reaches the page. The trace is shared with a role, never with a person
	(principle 14): the page sends the role, and shows the link the surface hands back.
-->
<script lang="ts">
	import { remove, send } from './api';
	import { clockOf, focused, followTrace, markOf, ROLE, shareAddress, traced } from './trace';
	import type { RunLevel, TraceLine, TraceView } from './types';

	let {
		level,
		base,
		named,
		motionAllowed,
		onRefused
	}: {
		level: RunLevel;
		base: URL;
		/** The step the address names, if it names one. */
		named?: string;
		motionAllowed: boolean;
		onRefused: () => void;
	} = $props();

	const steps = $derived(traced(level));
	let chosen = $state<string | null>(null);
	const stepId = $derived(chosen ?? focused(level, named));
	const stepState = $derived(level.steps.find((s) => s.id === stepId)?.state ?? '');

	let trace = $state<TraceView | null>(null);
	let lines = $state<TraceLine[]>([]);
	let absent = $state(false);
	let role = $state('');
	let said = $state<string | null>(null);
	let busy = $state(false);
	let copied = $state(false);

	// Read again whenever the step, or its state on the run level, changes: a step that runs
	// again after a stop reports again.
	$effect(() => {
		const step = stepId;
		void stepState;
		if (!step) return;
		const controller = new AbortController();
		absent = false;
		void followTrace({
			base,
			runId: level.run.id,
			stepId: step,
			signal: controller.signal,
			onTrace: (found, held) => {
				trace = found;
				lines = held;
			},
			onAbsent: () => {
				absent = true;
				trace = null;
				lines = [];
			},
			onRefused
		});
		return () => controller.abort();
	});

	const live = $derived(trace?.open ?? false);
	const roleValid = $derived(ROLE.test(role));
	const link = $derived(trace ? shareAddress(base, trace.link) : '');

	function pick(step: string) {
		chosen = step;
		trace = null;
		lines = [];
		said = null;
	}

	async function share(event: SubmitEvent) {
		event.preventDefault();
		if (!trace || !roleValid) return;
		busy = true;
		const path = `levels/runs/${encodeURIComponent(trace.run_id)}/steps/${encodeURIComponent(trace.step_id)}/trace/shares`;
		const answer = await send<TraceView>(base, path, { role });
		busy = false;
		if (answer.ok) {
			trace = { ...answer.body, lines: [] };
			said = `Shared with the role ${role}. Everyone who holds it, and may see this run, opens the link below.`;
			role = '';
		} else if (answer.problem.status === 401) onRefused();
		else said = `Not shared: ${answer.problem.detail || answer.problem.title}`;
	}

	async function withdraw(from: string) {
		if (!trace) return;
		busy = true;
		const path = `levels/runs/${encodeURIComponent(trace.run_id)}/steps/${encodeURIComponent(trace.step_id)}/trace/shares/${encodeURIComponent(from)}`;
		const answer = await remove<TraceView>(base, path);
		busy = false;
		if (answer.ok) {
			trace = { ...answer.body, lines: [] };
			said = `The role ${from} no longer opens this trace.`;
		} else if (answer.problem.status === 401) onRefused();
		else said = `Not withdrawn: ${answer.problem.detail || answer.problem.title}`;
	}

	async function copy() {
		try {
			await navigator.clipboard.writeText(link);
			copied = true;
			setTimeout(() => (copied = false), 1600);
		} catch {
			copied = false;
		}
	}
</script>

{#if steps.length}
	<section class="trace" aria-labelledby="trace-title">
		<header>
			<div>
				<p class="eyebrow">Inside the step</p>
				<h2 id="trace-title">What the worker is doing</h2>
			</div>
			{#if steps.length > 1}
				<div class="tabs" role="tablist" aria-label="Worker steps">
					{#each steps as step (step.id)}
						<button
							role="tab"
							aria-selected={step.id === stepId}
							class:on={step.id === stepId}
							onclick={() => pick(step.id)}>{step.id}</button
						>
					{/each}
				</div>
			{/if}
		</header>

		{#if absent}
			<p class="quiet">
				The trace of {stepId} is not shown to you. It is shown to the owner, and to a role it is shared with.
			</p>
		{:else if !trace}
			<p class="quiet">Reading the trace of {stepId}…</p>
		{:else}
			<p class="state" aria-live="polite">
				<span class="dot" class:live class:moving={live && motionAllowed} aria-hidden="true"></span>
				{#if live}
					{stepId} is working; new lines appear as the worker reports them.
				{:else}
					{stepId} {trace.state}: its trace as it was recorded.
				{/if}
			</p>

			{#if lines.length}
				<ol class="thread">
					{#each lines as line, i (line.position)}
						<li
							class="line"
							data-mark={markOf(line)}
							class:newest={live && motionAllowed && i === lines.length - 1}
						>
							<span class="mark" aria-hidden="true"></span>
							<time datetime={line.ts}>{clockOf(line.ts)}</time>
							<span class="text">{line.text}</span>
							<span class="kind">{line.type}</span>
						</li>
					{/each}
				</ol>
			{:else}
				<p class="quiet">The worker has reported nothing yet.</p>
			{/if}

			<form class="share" onsubmit={share}>
				<label>
					<span>Share with a role</span>
					<input
						bind:value={role}
						placeholder="reviewer"
						autocomplete="off"
						spellcheck="false"
						aria-invalid={role !== '' && !roleValid}
					/>
				</label>
				<button class="primary" disabled={busy || !roleValid}>Share</button>
				<p class="hint">A role, never a person: a lowercase name such as <code>reviewer</code>.</p>
			</form>

			{#if trace.shared_with?.length}
				<ul class="roles" aria-label="Shared with">
					{#each trace.shared_with as shared (shared)}
						<li>
							<span>{shared}</span>
							<button disabled={busy} onclick={() => withdraw(shared)}>Withdraw</button>
						</li>
					{/each}
				</ul>
				<p class="link">
					<code>{link}</code>
					<button onclick={copy}>{copied ? 'Copied' : 'Copy link'}</button>
				</p>
			{/if}
			{#if said}<p class="said" role="status">{said}</p>{/if}
		{/if}
	</section>
{/if}

<style>
	.trace {
		border: 1px solid var(--border-subtle);
		border-radius: var(--r-xl);
		padding: 1rem 1.1rem 1.1rem;
		margin: 1.25rem 0;
		background: var(--bg-canvas);
	}
	header {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: flex-end;
		gap: 0.75rem;
	}
	h2 {
		margin: 0;
		font-family: var(--font-display);
		font-weight: 500;
		font-size: var(--fs-400);
	}
	.tabs {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
	}
	.tabs button.on {
		background: var(--text-primary);
		color: var(--bg-canvas);
		border-color: var(--text-primary);
	}
	.quiet,
	.hint {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.state {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	.dot {
		width: 0.6rem;
		height: 0.6rem;
		border-radius: var(--r-full);
		border: 2px solid var(--family-waiting);
	}
	.dot.live {
		border-color: var(--family-variable);
		background: var(--family-variable);
	}
	.dot.moving {
		animation: breathe 1.6s ease-in-out infinite;
	}
	.thread {
		list-style: none;
		margin: 0.75rem 0 1rem;
		padding: 0 0 0 0.35rem;
		position: relative;
		max-height: 26rem;
		overflow-y: auto;
	}
	.thread::before {
		content: '';
		position: absolute;
		left: 0.85rem;
		top: 0.4rem;
		bottom: 0.4rem;
		width: 1px;
		background: var(--border-subtle);
	}
	.line {
		display: grid;
		grid-template-columns: 1.1rem 4.6rem 1fr auto;
		align-items: baseline;
		gap: 0.6rem;
		padding: 0.22rem 0;
		position: relative;
	}
	.mark {
		width: 0.7rem;
		height: 0.7rem;
		justify-self: center;
		align-self: center;
		background: var(--bg-canvas);
		border: 2px solid var(--family-variable);
		box-sizing: border-box;
		position: relative;
	}
	/* Each kind of event has a form of its own (UC-6.10: never colour alone). */
	[data-mark='start'] .mark {
		border-radius: var(--r-full);
	}
	[data-mark='say'] .mark {
		border-radius: var(--r-full);
		width: 0.45rem;
		height: 0.45rem;
		background: var(--family-variable);
	}
	[data-mark='call'] .mark {
		border-radius: var(--r-xs);
	}
	[data-mark='refused'] .mark {
		border-radius: var(--r-xs);
		border-color: var(--family-alert);
		background: linear-gradient(45deg, transparent 42%, var(--family-alert) 42% 58%, transparent 58%);
	}
	[data-mark='choice'] .mark {
		transform: rotate(45deg) scale(0.85);
	}
	[data-mark='use'] .mark {
		border-radius: var(--r-full);
		border-style: dotted;
	}
	[data-mark='boundary'] .mark {
		height: 0.25rem;
		width: 0.85rem;
		border-radius: var(--r-xs);
		background: var(--text-secondary);
		border-color: var(--text-secondary);
	}
	[data-mark='made'] .mark {
		border-radius: var(--r-xs) var(--r-xs) var(--r-xs) var(--r-xs);
		background: var(--bg-surface);
	}
	[data-mark='end'] .mark {
		border-radius: var(--r-full);
		background: var(--text-primary);
		border-color: var(--text-primary);
	}
	.newest .mark {
		animation: breathe 1.6s ease-in-out infinite;
	}
	.line:last-child .text {
		font-weight: 500;
	}
	time {
		font-family: var(--font-mono);
		font-size: var(--fs-075);
		color: var(--text-subtle);
		font-variant-numeric: tabular-nums;
	}
	.text {
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.kind {
		font-family: var(--font-mono);
		font-size: var(--fs-075);
		color: var(--text-subtle);
	}
	.share {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 0.5rem;
		border-top: 1px solid var(--border-subtle);
		padding-top: 0.85rem;
	}
	.share label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: var(--fs-100);
	}
	.share .hint {
		flex-basis: 100%;
		margin: 0;
	}
	input {
		font: inherit;
		font-family: var(--font-mono);
		padding: 0.4rem 0.7rem;
		border: 1px solid var(--border-subtle);
		border-radius: var(--r-md);
		background: var(--bg-canvas);
		color: var(--text-primary);
	}
	input[aria-invalid='true'] {
		border-color: var(--family-alert);
	}
	.roles {
		list-style: none;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin: 0.75rem 0 0.25rem;
	}
	.roles li {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		border: 1px solid var(--border-subtle);
		border-radius: var(--r-full);
		padding: 0.15rem 0.2rem 0.15rem 0.75rem;
		font-family: var(--font-mono);
		font-size: var(--fs-100);
	}
	.roles button {
		padding: 0.15rem 0.6rem;
		font-size: var(--fs-090);
	}
	.link {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.link code {
		background: var(--bg-surface);
		border-radius: var(--r-md);
		padding: 0.3rem 0.55rem;
		overflow-wrap: anywhere;
		font-size: var(--fs-090);
	}
	.said {
		font-size: var(--fs-100);
		color: var(--text-secondary);
	}
	@keyframes breathe {
		0%,
		100% {
			box-shadow: 0 0 0 0 color-mix(in oklch, var(--family-variable) 45%, transparent);
		}
		50% {
			box-shadow: 0 0 0 0.35rem color-mix(in oklch, var(--family-variable) 0%, transparent);
		}
	}
	@media (max-width: 640px) {
		.line {
			grid-template-columns: 1.1rem 1fr;
		}
		.line time,
		.line .kind {
			grid-column: 2;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.dot.moving,
		.newest .mark {
			animation: none;
		}
	}
</style>
