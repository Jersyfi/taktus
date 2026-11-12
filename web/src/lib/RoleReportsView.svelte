<!--
	The reports for a role (UC-6.2, ADR-0242): each report the reader's roles read, with its
	reader role, when it comes and the channel; and a button that has the surface compose it now
	and shows its lines. A quiet period is one sentence. Nothing here computes a figure.
-->
<script lang="ts">
	import { triggerLine, type ComposedReport, type Definitions } from './figures';

	let {
		definitions,
		composed = {},
		problems = {},
		busy = null,
		onCompose
	}: {
		definitions: Definitions;
		/** Each report composed so far, by its id. */
		composed?: Record<string, ComposedReport>;
		/** What the surface said where it composed a report not, by its id. */
		problems?: Record<string, string>;
		busy?: string | null;
		onCompose: (id: string) => void;
	} = $props();

	const sentence = $derived(
		definitions.definitions.length === 0
			? 'No report is set up for your roles.'
			: `${definitions.definitions.length} ${definitions.definitions.length === 1 ? 'report' : 'reports'} for your roles.`
	);
</script>

<section aria-labelledby="role-reports-title">
	<p class="eyebrow">Reports</p>
	<h1 id="role-reports-title">{sentence}</h1>

	<ul class="reports">
		{#each definitions.definitions as d (d.id)}
			<li data-report={d.id}>
				<div class="head">
					<div>
						<h2>{d.id}</h2>
						<p class="muted">For the role {d.reader_role}, {triggerLine(d)}, by {d.channel}.</p>
					</div>
					<button type="button" disabled={busy === d.id} onclick={() => onCompose(d.id)}>Compose it now</button>
				</div>
				{#if problems[d.id]}
					<p role="alert">{problems[d.id]}</p>
				{/if}
				{#if composed[d.id]}
					{@const r = composed[d.id]!}
					<section aria-label={`${d.id} now`}>
						<h3>{r.title}</h3>
						<ol class="lines">
							{#each r.lines as line, i (i)}<li>{line}</li>{/each}
						</ol>
					</section>
				{/if}
			</li>
		{/each}
	</ul>
</section>

<style>
	.reports {
		list-style: none;
		padding: 0;
		max-width: 48rem;
	}
	.reports > li {
		padding: var(--sp-200) 0;
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		gap: var(--sp-100) var(--sp-300);
		justify-content: space-between;
		align-items: center;
	}
	h2 {
		margin: 0;
		font-family: var(--font-mono);
		font-size: var(--fs-100);
	}
	.muted {
		margin: var(--sp-050) 0 0;
		color: var(--text-secondary);
	}
	.lines li {
		padding: var(--sp-050) 0;
	}
</style>
