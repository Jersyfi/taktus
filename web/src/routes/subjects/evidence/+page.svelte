<!--
	The processing evidence (ADR-0176 §8): `GET /evidence`, read once on opening. Generated from the
	register of what acts, the tenant's declarations, its trace retention and the ledger; the page
	shows its notice first, because it is not legally reviewed.
-->
<script lang="ts">
	import Unavailable from '../../../lib/Unavailable.svelte';
	import { read, surface } from '../../../lib/api';
	import SignInForm from '../../../lib/SignInForm.svelte';
	import { evidenceSentence, subjectsLink, type ProcessingEvidence } from '../../../lib/subjects';

	let signedIn = $state(true);
	let found: ProcessingEvidence | null = $state(null);
	let problem: string | null = $state(null);

	$effect(() => {
		if (!signedIn) return;
		void read<ProcessingEvidence>(surface(location.href), 'evidence').then((answer) => {
			if (answer.ok) found = answer.body;
			else if (answer.problem.status === 401) signedIn = false;
			else problem = answer.problem.detail || answer.problem.title;
		});
	});
</script>

{#if !signedIn}
	<SignInForm onSignedIn={() => (signedIn = true)} />
{:else if found}
	<section aria-labelledby="evidence-title">
		<p class="eyebrow"><a href={subjectsLink}>Data protection</a> · Processing evidence</p>
		<h1 id="evidence-title">{evidenceSentence(found)}</h1>
		<p class="notice" role="note">{found.notice}</p>
		<p class="muted">Generated {found.generated_at.slice(0, 16).replace('T', ' ')}. Residency rule: {found.residency_rule}.</p>
		<h2>Steps that process personal data</h2>
		<table>
			<thead><tr><th>Process</th><th>Step</th><th>Why personal</th><th>Adapter</th><th>Where</th></tr></thead>
			<tbody>
				{#each found.personal_data_steps as s (`${s.process}:${s.step}:${s.adapter}`)}
					<tr>
						<td>{s.process}@{s.version}</td><td>{s.step}</td><td>{s.personal_data}</td><td>{s.adapter}</td>
						<td>{s.location}{s.within_residency_rule === false ? ' — outside the rule' : ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<h2>How long each record is kept</h2>
		<ul>
			{#each found.keeping as k (k.record)}<li><strong>{k.record}</strong>: {k.holds}. Kept {k.kept}.</li>{/each}
		</ul>
		<h2>Requests answered</h2>
		<p>
			{found.requests.prepared} prepared, {found.requests.erased} erased, {found.requests.exported} exported,
			{found.requests.rectified} rectified, {found.requests.withdrawn} withdrawn.
		</p>
	</section>
{:else if problem}
	<Unavailable eyebrow="Processing evidence" {problem} />
{:else}
	<p class="status">Generating the processing evidence…</p>
{/if}

<style>
	.status,
	.muted {
		color: var(--text-secondary);
		font-size: 0.9rem;
	}
	.notice {
		max-width: 46rem;
		padding: 0.6rem 0.8rem;
		border-left: 3px solid var(--border-subtle);
	}
	table {
		border-collapse: collapse;
		font-size: 0.88rem;
		display: block;
		overflow-x: auto;
	}
	th,
	td {
		text-align: left;
		padding: 0.35rem 0.6rem;
		border-bottom: 1px solid var(--border-subtle);
	}
</style>
