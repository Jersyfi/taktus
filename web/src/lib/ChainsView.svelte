<!--
	End-to-end chains across domains (UC-15.4, ADR-0301 §4). Each chain as a whole: its links in
	order, what passes at every boundary with the clause that requires it, its own objectives,
	and its latest run with where it stands. A halted handover takes the person's decision: a
	value for every item it lacked, or a stop (ADR-0302 §3). No figure names a person.
-->
<script lang="ts">
	import { send, surface } from './api';
	import { decisionPath, objectives, standing, type ChainList, type ChainRunView } from './chains';

	let { view }: { view: ChainList } = $props();

	let given: Record<string, Record<string, string>> = $state({});
	let said: Record<string, string> = $state({});

	async function decide(run: ChainRunView, stop: boolean): Promise<void> {
		const body = stop ? { stop: true } : { given: given[run.id] ?? {} };
		const answer = await send<ChainRunView>(surface(location.href), decisionPath(run.id), body);
		said[run.id] = answer.ok
			? `The chain is ${answer.body.state} now.`
			: answer.problem.detail || answer.problem.title;
	}

	function typed(run: ChainRunView, input: string, value: string): void {
		given[run.id] = { ...(given[run.id] ?? {}), [input]: value };
	}
</script>

<section class="chains" aria-labelledby="chains-title">
	<p class="eyebrow">Chains across domains</p>
	<h1 id="chains-title">
		{view.chains.length
			? `${view.chains.length} chain(s) link processes across domains`
			: 'No chain is declared'}
	</h1>
	{#each view.chains as chain (chain.id)}
		<article class="chain" data-chain={chain.id}>
			<h2>{chain.name}</h2>
			{#if objectives(chain)}<p class="muted">Its own objectives: {objectives(chain)}.</p>{/if}
			<ol class="links">
				{#each chain.links as link, index (link.process_version)}
					<li>
						{#if link.handover?.length}
							<ul class="handover" aria-label="Handed over to link {index + 1}">
								{#each link.handover as item (item.input)}
									<li><code>{item.input}</code> from {item.step}: {item.clause}</li>
								{/each}
							</ul>
						{/if}
						<p class="link">{link.process_version}</p>
					</li>
				{/each}
			</ol>
			{#each chain.runs as run (run.id)}
				<div class="run {run.state}">
					<p>{standing(chain, run)}</p>
					{#if run.reason && run.state !== 'finished'}<p class="muted">{run.reason}</p>{/if}
					{#if run.measured}<p class="muted">Objectives: {run.measured}</p>{/if}
					{#if run.state === 'halted'}
						<form onsubmit={(event) => { event.preventDefault(); void decide(run, false); }}>
							{#each run.missing as input (input)}
								<label>
									{input}
									<input
										value={given[run.id]?.[input] ?? ''}
										oninput={(event) => typed(run, input, event.currentTarget.value)}
										required
									/>
								</label>
							{/each}
							<button type="submit">Give and go on</button>
							<button type="button" onclick={() => decide(run, true)}>Stop the chain</button>
						</form>
					{/if}
					{#if said[run.id]}<p role="status">{said[run.id]}</p>{/if}
				</div>
			{:else}
				<p class="muted">Not run yet.</p>
			{/each}
		</article>
	{/each}
	<p class="muted">No figure names a person.</p>
</section>

<style>
	.chain {
		border: 1px solid var(--border-subtle);
		border-radius: var(--r-md);
		padding: 1rem;
		margin-block: 1rem;
	}
	.links {
		list-style: none;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: flex-end;
	}
	.link {
		font-weight: 600;
		margin: 0;
	}
	.handover {
		font-size: var(--fs-100);
		color: var(--text-secondary);
		padding-left: 1rem;
	}
	.run {
		border-top: 1px solid var(--border-subtle);
		padding-top: 0.5rem;
	}
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-100);
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: flex-end;
	}
</style>
