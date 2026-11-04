<!--
	The model trials (#448, ADR-0149): the trials offered now, each startable with the candidates
	it names, a trial started by hand, and every trial of the tenant. A trial is offered, never
	started on its own; starting one runs rehearsals and binds no model.
-->
<script lang="ts">
	import OperationPage from './OperationPage.svelte';
	import { MAX_NAMED, namedCases, occasion, offerLine, trialsLink, type NamedCase, type Offer, type Trials } from './spend';

	let {
		trials,
		onStart,
		onDecline = () => {},
		problem = null
	}: {
		trials: Trials;
		onStart: (purpose: string, candidates: string[], occasion: string, cases?: NamedCase[]) => void;
		onDecline?: (offer: Offer, reason: string) => void;
		problem?: string | null;
	} = $props();

	let purpose = $state('');
	let candidates = $state('');
	let rows: { process: string; inputs: string }[] = $state([]);
	let declining: string | null = $state(null);
	let reason = $state('');
	const named = $derived(namedCases(rows));
	const key = (o: Offer) => `${o.purpose}/${o.occasion}/${o.model}`;
	const offered = $derived(trials.offers.length);
	const sentence = $derived(
		offered === 0
			? `No trial is offered now; ${trials.trials.length} ${trials.trials.length === 1 ? 'trial was' : 'trials were'} run.`
			: `${offered} ${offered === 1 ? 'trial is' : 'trials are'} offered; ${trials.trials.length} ${trials.trials.length === 1 ? 'was' : 'were'} run.`
	);
	const lines = $derived([
		...trials.offers.map(offerLine),
		...trials.trials.map((t) => `${t.id}: ${t.purpose}, ${t.candidates.join(', ')}, ${occasion(t.occasion)}.`)
	]);
	function start(offer: Offer) {
		onStart(offer.purpose, offer.candidates, offer.occasion);
	}
</script>

<OperationPage eyebrow="Model trials" {sentence} {lines}>
	{#if problem}<p class="mark look" role="alert">{problem}</p>{/if}
	{#if trials.offers.length > 0}
		<h2>Offered</h2>
		<ul class="records">
			{#each trials.offers as offer (offer.purpose + offer.occasion + offer.model)}
				<li class="record">
					<p class="mark">{occasion(offer.occasion)}</p>
					<h3>{offer.purpose}</h3>
					<p class="meta">{offer.reason}</p>
					<p class="meta">Compares {offer.candidates.join(', ')}</p>
					{#if declining === key(offer)}
						<form
							class="start"
							onsubmit={(event) => {
								event.preventDefault();
								onDecline(offer, reason.trim());
								declining = null;
								reason = '';
							}}
						>
							<label>Why, in your words (optional) <input bind:value={reason} maxlength="500" autocomplete="off" /></label>
							<button type="submit">Decline the offer</button>
							<button type="button" class="quiet" onclick={() => (declining = null)}>Keep it</button>
						</form>
						<p class="meta">A declined offer is not shown again until its occasion arises anew, for everyone of the tenant.</p>
					{:else}
						<div class="acts">
							<button type="button" onclick={() => start(offer)} disabled={offer.candidates.length === 0}>Run the trial</button>
							<button type="button" class="quiet" onclick={() => (declining = key(offer))}>Decline…</button>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
	<h2>Run a trial</h2>
	<form
		class="start"
		onsubmit={(event) => {
			event.preventDefault();
			const models = candidates.split(/[\s,]+/).filter(Boolean);
			if (purpose.trim() && models.length > 0 && named.ok) onStart(purpose.trim(), models, 'asked', named.cases);
		}}
	>
		<label>Purpose <input bind:value={purpose} placeholder="drafting" autocomplete="off" /></label>
		<label>Candidates <input bind:value={candidates} placeholder="model.a, model.b" autocomplete="off" /></label>
		<fieldset class="cases">
			<legend>Cases of your own, beside the evaluation cases (at most {MAX_NAMED})</legend>
			{#each rows as row, i (i)}
				<div class="case">
					<label>Process <input bind:value={row.process} placeholder="replies" autocomplete="off" /></label>
					<label>Inputs, as JSON <textarea bind:value={row.inputs} rows="2" placeholder={'{"message": "late"}'}></textarea></label>
					<button type="button" class="quiet" onclick={() => (rows = rows.filter((_, j) => j !== i))}>Remove</button>
				</div>
			{/each}
			<button type="button" class="quiet" disabled={rows.length >= MAX_NAMED} onclick={() => (rows = [...rows, { process: '', inputs: '{}' }])}>
				Add a case
			</button>
			{#if !named.ok}<p class="mark look" role="alert">{named.problem}</p>{/if}
		</fieldset>
		<button type="submit" disabled={!purpose.trim() || !candidates.trim() || !named.ok}>Run the trial</button>
	</form>
	<p class="meta">
		Every evaluation case of the processes that ask for the purpose runs once per candidate, as a rehearsal, and so does every
		case you name. A case you name has no target: it passes when its run ends well. Nothing outside is acted on, and no model is
		bound.
	</p>
	<h2>Run</h2>
	{#if trials.trials.length === 0}
		<p class="empty">No trial yet.</p>
	{:else}
		<ul class="records">
			{#each trials.trials as trial (trial.id)}
				<li class="record">
					<p class="mark">{occasion(trial.occasion)}</p>
					<h3><a href={trialsLink(trial.id)}>{trial.purpose}</a></h3>
					<p class="meta">{trial.candidates.join(', ')}</p>
					<p class="id">{trial.id} · {new Date(trial.started_at).toLocaleString('en')}</p>
				</li>
			{/each}
		</ul>
	{/if}
</OperationPage>

<style>
	.start {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: end;
	}
	.acts {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.cases {
		display: grid;
		gap: 0.5rem;
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		padding: 0.5rem 0.75rem;
		flex-basis: 100%;
	}
	.case {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: end;
	}
	textarea {
		font: inherit;
		font-family: var(--font-mono);
		padding: 0.35rem 0.6rem;
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		background: var(--bg-canvas);
		color: var(--text-primary);
		min-width: min(20rem, 100%);
	}
	label {
		display: grid;
		gap: 0.25rem;
		font-size: 0.85rem;
		color: var(--text-secondary);
	}
	input {
		font: inherit;
		font-family: var(--font-mono);
		padding: 0.35rem 0.6rem;
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		background: var(--bg-canvas);
		color: var(--text-primary);
	}
</style>
