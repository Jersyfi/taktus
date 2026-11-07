<!--
	The plan dialogue (UC-1.2, ADR-0237) in the guided and the expert mode (UC-13.1, ADR-0238), and
	the guided start of a person who is not technical (UC-10.3). Without a draft it asks what the
	person wants to automate. With one, the guided mode asks one question at a time, explaining
	its term where it first appears, and the expert mode shows every field at once; both change
	the one draft, so switching loses nothing. Every setting is shown with its value and why.
	Commissioning is a button of its own, refused with what is missing. The page computes nothing.
-->
<script lang="ts">
	import type { Mode, PlanDraftView, Template } from './workspace';
	import { answerValue } from './workspace';

	let {
		view = null,
		plans = [],
		templates = [],
		busy = false,
		message = null,
		onOpen,
		onPick,
		onAnswer,
		onSet,
		onMode,
		onCommission
	}: {
		view?: PlanDraftView | null;
		plans?: PlanDraftView[];
		templates?: Template[];
		busy?: boolean;
		message?: string | null;
		onOpen: (said: string) => void;
		onPick: (draftId: string) => void;
		onAnswer: (field: string, value: unknown, stepId: string | null) => void;
		onSet: (fields: Record<string, unknown>) => void;
		onMode: (mode: Mode) => void;
		onCommission: () => void;
	} = $props();

	let said = $state('');
	let typed = $state('');
	let fields: Record<string, string> = $state({});

	function open(event: SubmitEvent) {
		event.preventDefault();
		onOpen(said);
	}

	function answer(event: SubmitEvent) {
		event.preventDefault();
		if (!view?.question) return;
		onAnswer(view.question.field, answerValue(view.question, typed), view.question.step_id);
		typed = '';
	}

	function set(event: SubmitEvent) {
		event.preventDefault();
		const given: Record<string, unknown> = {};
		for (const [name, value] of Object.entries(fields)) {
			if (!value.trim()) continue;
			given[name] = name === 'autonomy_level' ? Number(value) : name === 'steps' ? { process_version: value } : value;
		}
		onSet(given);
		fields = {};
	}

	const WORDS: Record<string, string> = {
		goal: 'What should be achieved',
		steps: 'What does the work',
		due: 'By when',
		autonomy_level: 'How much Taktus does on its own (its autonomy level)',
		autonomy_reason: 'Why that much',
		estimates: 'How long each step takes (its estimate)',
		results_in: 'What the plan ends in',
		process_version: 'The template chosen'
	};

	const EXPERT_FIELDS: { name: string; label: string }[] = [
		{ name: 'goal', label: 'Goal' },
		{ name: 'steps', label: 'Process version (process@version)' },
		{ name: 'due', label: 'Due (2026-12-01)' },
		{ name: 'autonomy_level', label: 'Autonomy level (1 to 4)' },
		{ name: 'autonomy_reason', label: 'Why that level' }
	];
</script>

<section class="plan" aria-labelledby="plan-title">
	<p class="eyebrow">Plan · worked out together</p>
	{#if message}<p class="message" aria-live="polite">{message}</p>{/if}

	{#if !view}
		<h1 id="plan-title">What would you like to automate?</h1>
		<p class="muted">
			Say it in your own words. Taktus asks what it still needs, one question at a time, and explains every term
			it uses. Nothing runs until you say so.
		</p>
		<form class="start" onsubmit={open} data-start>
			<label>
				In one sentence
				<input type="text" name="said" bind:value={said} placeholder="Send the weekly report to the team every Monday" />
			</label>
			<button type="submit" class="primary" disabled={busy || !said.trim()}>Start</button>
		</form>
		{#if plans.length}
			<h2>Your plans</h2>
			<ul class="plans">
				{#each plans as p (p.draft.id)}
					<li>
						<button type="button" class="quiet" onclick={() => onPick(p.draft.id)}>
							{p.draft.goal ?? 'A plan without a goal yet'} · version {p.draft.version}{p.commissioned ? ' · commissioned' : ''}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	{:else}
		<h1 id="plan-title">{view.draft.goal ?? 'A new plan'}</h1>
		<p class="muted">
			Version {view.draft.version}{view.commissioned ? ', commissioned' : ', not commissioned'}.
			<span role="group" aria-label="Mode">
				<button type="button" class="quiet" aria-pressed={view.mode === 'guided'} onclick={() => onMode('guided')}>Guided</button>
				<button type="button" class="quiet" aria-pressed={view.mode === 'expert'} onclick={() => onMode('expert')}>Expert</button>
			</span>
		</p>

		{#if view.mode === 'guided' && view.question}
			<form class="question" onsubmit={answer} data-question={view.question.field}>
				<p class="asks">{view.question.asks}</p>
				{#if view.question.explains}<p class="explains">{view.question.explains}</p>{/if}
				{#if view.question.field === 'steps' && templates.length}
					<ul class="templates">
						{#each templates as t (t.ref)}
							<li>
								<button type="button" disabled={busy} onclick={() => onAnswer('steps', { process_version: t.ref }, null)}>
									{t.name} — starts at level {t.level}
								</button>
							</li>
						{/each}
					</ul>
				{/if}
				<label>
					Your answer
					<input type="text" name="answer" bind:value={typed} />
				</label>
				<button type="submit" disabled={busy || !typed.trim()}>Answer</button>
			</form>
		{:else if view.mode === 'expert'}
			<form class="fields" onsubmit={set} data-expert>
				{#each EXPERT_FIELDS as f (f.name)}
					<label>
						{f.label}
						<input type="text" name={f.name} value={fields[f.name] ?? ''} oninput={(e) => (fields[f.name] = (e.currentTarget as HTMLInputElement).value)} />
					</label>
				{/each}
				<button type="submit" disabled={busy}>Set</button>
			</form>
		{/if}

		<h2>Every setting</h2>
		<dl class="settings">
			{#each view.settings as s (s.field)}
				<dt data-setting={s.field}>{WORDS[s.field] ?? s.field}{s.asked ? '' : ' (not asked)'}</dt>
				<dd>{s.value} — {s.why}</dd>
			{/each}
		</dl>

		{#if view.estimates.length}
			<h2>Estimates</h2>
			<ul>{#each view.estimates as e (e)}<li>{e}</li>{/each}</ul>
		{/if}

		{#if view.missing.length}
			<p class="muted" data-missing>Still missing: {view.missing.join('; ')}.</p>
		{/if}
		{#if view.mode === 'guided'}
			<p class="muted" data-explains="commission">
				Commissioning means you say: run it as planned. Nothing runs before you do, and a changed plan needs it
				again.
			</p>
		{/if}
		<button type="button" class="primary" disabled={busy || view.commissioned} onclick={onCommission}>
			Commission version {view.draft.version}
		</button>
	{/if}
</section>

<style>
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	form {
		display: grid;
		gap: var(--sp-150);
		margin-top: var(--sp-200);
		max-width: 40rem;
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
		color: var(--text-primary);
	}
	.asks {
		font-size: var(--fs-300);
		font-weight: var(--fw-semibold);
		margin: 0;
	}
	.explains {
		color: var(--text-secondary);
		border-inline-start: 3px solid var(--accent-primary);
		padding-inline-start: var(--sp-150);
		margin: 0;
	}
	.templates,
	.plans {
		list-style: none;
		padding: 0;
		display: grid;
		gap: var(--sp-100);
	}
	.settings {
		display: grid;
		grid-template-columns: minmax(8rem, max-content) 1fr;
		gap: var(--sp-100) var(--sp-200);
		font-size: var(--fs-100);
	}
	.settings dt {
		font-weight: var(--fw-semibold);
	}
	.settings dd {
		margin: 0;
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
