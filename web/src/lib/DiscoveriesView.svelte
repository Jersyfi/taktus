<!--
	Processes nobody wrote down (UC-9.4, ADR-0245 §2): every one the organisation brought to light,
	and the patterns found for the reader, which only they see until they agree. A process is made
	visible from a short form, or written down from the interview — guided with an example per
	question, or expert without —, and each record is taken to its next stage. Whether a stage may
	follow is the surface's to say; a refusal is shown in its words. The decision to automate is a
	person's. No record says whose a pattern is.
-->
<script lang="ts">
	import {
		discoveredLine,
		mine,
		nextStage,
		STAGE_FIELDS,
		stageBody,
		STAGES,
		type Discoveries,
		type Discovered,
		type Interview,
		type Interviewed,
		type Mode,
		type Origin,
		type Stage
	} from './discoveries';

	let {
		discoveries,
		interview,
		interviewed = null,
		problem = null,
		busy = false,
		onDiscover,
		onMode,
		onInterview,
		onAdvance,
		onAgree
	}: {
		discoveries: Discoveries;
		interview: Interview | null;
		interviewed?: Interviewed | null;
		problem?: string | null;
		busy?: boolean;
		onDiscover: (body: { title: string; origin: Origin; found: string }) => void;
		onMode: (mode: Mode) => void;
		onInterview: (answers: Record<string, string>) => void;
		onAdvance: (id: string, stage: Exclude<Stage, 'visible'>, body: Record<string, unknown>) => void;
		onAgree: (id: string) => void;
	} = $props();

	let title = $state('');
	let origin = $state<Origin>('request');
	let found = $state('');
	let answers = $state<Record<string, string>>({});
	let values = $state<Record<string, Record<string, string>>>({});

	const sentence = $derived(
		discoveries.discoveries.length === 0
			? 'No process has been brought to light yet.'
			: `${discoveries.discoveries.length} ${discoveries.discoveries.length === 1 ? 'process' : 'processes'} brought to light.`
	);

	function field(id: string, key: string): string {
		return values[id]?.[key] ?? '';
	}
	function set(id: string, key: string, value: string) {
		values = { ...values, [id]: { ...(values[id] ?? {}), [key]: value } };
	}
	function advance(d: Discovered) {
		const stage = nextStage(d.stage);
		if (stage) onAdvance(d.id, stage, stageBody(stage, values[d.id] ?? {}));
	}
</script>

<section aria-labelledby="discoveries-title">
	<p class="eyebrow">Discoveries</p>
	<h1 id="discoveries-title">{sentence}</h1>
	{#if problem}<p role="alert">{problem}</p>{/if}

	<ul class="records">
		{#each discoveries.discoveries as d (d.id)}
			{@const next = nextStage(d.stage)}
			<li data-discovery={d.id}>
				<div class="head">
					<strong>{d.title}</strong>
					<span class="stage">{d.stage}, stage {STAGES.indexOf(d.stage) + 1} of {STAGES.length}</span>
				</div>
				<p class="muted">{discoveredLine(d)} {d.found}</p>
				{#if d.description}<p class="description">{d.description}</p>{/if}
				{#if mine(d)}
					<p class="private" data-private>Found for you; only you see it until you agree.</p>
					<button type="button" disabled={busy} onclick={() => onAgree(d.id)}>Agree it becomes the organisation's procedure</button>
				{:else if next}
					<form
						class="stage-form"
						onsubmit={(event) => {
							event.preventDefault();
							advance(d);
						}}
					>
						<p class="muted">Next: {next}.</p>
						{#each STAGE_FIELDS[next] as f (f.key)}
							<label for={`${d.id}-${f.key}`}>{f.label}</label>
							{#if f.kind === 'long'}
								<textarea id={`${d.id}-${f.key}`} rows="3" value={field(d.id, f.key)} oninput={(e) => set(d.id, f.key, e.currentTarget.value)}></textarea>
							{:else if f.kind === 'choice'}
								<select id={`${d.id}-${f.key}`} value={field(d.id, f.key)} onchange={(e) => set(d.id, f.key, e.currentTarget.value)}>
									<option value="">Choose…</option>
									{#each f.choices ?? [] as c (c)}<option value={c}>{c}</option>{/each}
								</select>
							{:else}
								<input
									id={`${d.id}-${f.key}`}
									type={f.kind === 'number' ? 'number' : 'text'}
									value={field(d.id, f.key)}
									oninput={(e) => set(d.id, f.key, e.currentTarget.value)}
									autocomplete="off"
								/>
							{/if}
						{/each}
						<button type="submit" disabled={busy}>Take it to {next}</button>
					</form>
				{/if}
			</li>
		{/each}
	</ul>

	<form
		class="discover"
		onsubmit={(event) => {
			event.preventDefault();
			onDiscover({ title: title.trim(), origin, found: found.trim() });
		}}
	>
		<h2>Make a process visible</h2>
		<label for="discover-title">What it is called</label>
		<input id="discover-title" bind:value={title} autocomplete="off" />
		<label for="discover-origin">Where it was found</label>
		<select id="discover-origin" bind:value={origin}>
			<option value="request">From a request</option>
			<option value="interview">From an interview</option>
			<option value="pattern">A pattern in your own requests (only you see it)</option>
		</select>
		<label for="discover-found">What was found and where, as a procedure</label>
		<textarea id="discover-found" rows="3" bind:value={found}></textarea>
		<button type="submit" disabled={busy || !title.trim() || !found.trim()}>Make it visible</button>
	</form>

	<section class="interview" aria-labelledby="interview-title">
		<h2 id="interview-title">The interview</h2>
		<div class="modes" role="group" aria-label="How the questions are asked">
			<button type="button" aria-pressed={interview?.mode === 'guided'} onclick={() => onMode('guided')}>Guided</button>
			<button type="button" aria-pressed={interview?.mode === 'expert'} onclick={() => onMode('expert')}>Expert</button>
		</div>
		{#if interview}
			<form
				onsubmit={(event) => {
					event.preventDefault();
					onInterview(answers);
				}}
			>
				{#each interview.questions as q (q.key)}
					<label for={`interview-${q.key}`}>{q.question}</label>
					<input
						id={`interview-${q.key}`}
						value={answers[q.key] ?? ''}
						oninput={(e) => (answers = { ...answers, [q.key]: e.currentTarget.value })}
						placeholder={q.example ?? ''}
						autocomplete="off"
					/>
				{/each}
				<button type="submit" disabled={busy}>Write it down</button>
			</form>
		{/if}
		{#if interviewed}
			<section aria-label="The documented process">
				<h3>Written down</h3>
				<pre>{interviewed.description}</pre>
				<p class="muted">Responsible role: {interviewed.owner_role}. Take a record to documented with this text.</p>
			</section>
		{/if}
	</section>
</section>

<style>
	.records {
		list-style: none;
		padding: 0;
		max-width: 48rem;
	}
	.records > li {
		padding: var(--sp-200) 0;
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: var(--sp-100) var(--sp-300);
	}
	.stage {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
	.muted {
		color: var(--text-secondary);
	}
	.description {
		white-space: pre-line;
	}
	.private {
		display: inline-block;
		font-size: var(--fs-075);
		padding: var(--sp-050) var(--sp-150);
		border-radius: var(--r-full);
		border: var(--bw-hairline) solid var(--border-subtle);
		color: var(--text-secondary);
	}
	form {
		display: flex;
		flex-direction: column;
		gap: var(--sp-100);
		max-width: 32rem;
	}
	.discover,
	.interview {
		margin-top: var(--sp-300);
	}
	label {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
	form button {
		align-self: flex-start;
	}
	.modes {
		display: flex;
		gap: var(--sp-100);
		margin-bottom: var(--sp-150);
	}
	pre {
		white-space: pre-wrap;
		font-family: var(--font-mono);
		font-size: var(--fs-075);
	}
</style>
