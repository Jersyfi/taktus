<!--
	The reader's views (UC-6.4, ADR-0241): each view their roles hold, or that was given to them,
	with the figures their roles are entitled to. Every figure here is one of the export, which is
	read as CSV or JSON from the links below. Nothing here computes a figure, and no view groups
	by a person.
-->
<script lang="ts">
	import FigureList from './FigureList.svelte';
	import { EXPORT_CSV, EXPORT_JSON, figureLine, viewsSentence, type Views } from './figures';

	let { views }: { views: Views } = $props();
</script>

<section aria-labelledby="views-title">
	<p class="eyebrow">Figures</p>
	<h1 id="views-title">{viewsSentence(views)}</h1>
	<p class="export">
		Every figure you may read, for any tool: <a href={EXPORT_CSV} download>figures.csv</a> ·
		<a href={EXPORT_JSON}>figures as JSON</a>
	</p>

	{#each views.views as view (view.id)}
		<section aria-labelledby={`view-${view.id}`}>
			<h2 id={`view-${view.id}`}>{view.title}</h2>
			<p class="muted">Grouped by {view.group_by}.</p>
			<FigureList figures={view.figures} />
		</section>
	{/each}

	<section class="text" aria-label="This page as text">
		<h2>As text</h2>
		<ol>
			<li>{viewsSentence(views)}</li>
			{#each views.views as view (view.id)}
				{#each view.figures as f (`${view.id}:${f.id}:${f.scope}:${f.subject}`)}
					<li>{view.title}: {figureLine(f)}</li>
				{/each}
			{/each}
		</ol>
	</section>
</section>

<style>
	.export {
		color: var(--text-secondary);
	}
	.muted {
		color: var(--text-secondary);
		font-size: var(--fs-075);
	}
</style>
