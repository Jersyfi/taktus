<!--
	A chart of steps as horizontal bars, one row per step (#449, ADR-0148). One measure per chart,
	on one axis that starts at zero: money, or tokens split by price kind. With two series — two
	runs, or two candidates — each row holds a bar per series, each named in the legend and at its
	end. Every bar says its figure on hover and to a screen reader; the page's text equivalent
	holds the same figures as a list. Hues are added on top of the form, never alone (DEC-0185).
-->
<script lang="ts">
	import { KIND_NAMES, KINDS, count, type Row } from './spend';

	let {
		title,
		rows,
		series = [],
		kinds = false
	}: { title: string; rows: Row[]; series?: string[]; kinds?: boolean } = $props();

	const used = $derived(
		kinds ? KINDS.filter((k) => rows.some((r) => r.bars.some((b) => b.parts?.some((p) => p.kind === k)))) : []
	);
</script>

<figure class="chart">
	<figcaption>{title}</figcaption>
	{#if series.length > 1 || used.length > 0}
		<ul class="legend">
			{#each series as name, i (name)}
				{#if series.length > 1}<li><span class="swatch" data-series={i + 1}></span>{name}</li>{/if}
			{/each}
			{#each used as kind (kind)}
				<li><span class="swatch" data-kind={kind}></span>{KIND_NAMES[kind]}</li>
			{/each}
		</ul>
	{/if}
	<div class="rows" role="list">
		{#each rows as row (row.step)}
			<div class="row" role="listitem">
				<span class="step">{row.step}</span>
				<div class="bars">
					{#each row.bars as bar (bar.series)}
						<div class="track" title="{row.step}{series.length > 1 ? `, ${series[bar.series]}` : ''}: {bar.label}">
							{#if bar.share > 0}
								<span
									class="bar"
									class:split={!!bar.parts?.length}
									data-series={bar.series + 1}
									style:width="{Math.max(bar.share * 100, 1.5)}%"
									role="img"
									aria-label="{row.step}{series.length > 1 ? `, ${series[bar.series]}` : ''}: {bar.label}"
								>
									{#each bar.parts ?? [] as part (part.kind)}
										<span
											class="part"
											data-kind={part.kind}
											style:flex-grow={part.share}
											title="{KIND_NAMES[part.kind]}: {count(part.tokens)}"
										></span>
									{/each}
								</span>
							{/if}
							<span class="value">{bar.label}</span>
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>
</figure>

<style>
	.chart {
		margin: 0 0 2rem;
		max-width: 52rem;
		/* The reference categorical order, validated for both surfaces (dataviz palette). */
		--series-1: #2a78d6;
		--series-2: #eb6834;
		--kind-input: #2a78d6;
		--kind-cache_write: #eb6834;
		--kind-cache_read: #1baf7a;
		--kind-output: #eda100;
	}
	@media (prefers-color-scheme: dark) {
		.chart {
			--series-1: #3987e5;
			--series-2: #d95926;
			--kind-input: #3987e5;
			--kind-cache_write: #d95926;
			--kind-cache_read: #199e70;
			--kind-output: #c98500;
		}
	}
	figcaption {
		font-size: 0.8rem;
		font-weight: 500;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-2);
		margin-bottom: 0.6rem;
	}
	.legend {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem 1.1rem;
		padding: 0;
		margin: 0 0 0.8rem;
		font-size: 0.85rem;
		color: var(--ink-2);
	}
	.legend li {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.swatch {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 3px;
	}
	.rows {
		display: grid;
		gap: 0.55rem;
	}
	.row {
		display: grid;
		grid-template-columns: minmax(6rem, 10rem) 1fr;
		gap: 0.75rem;
		align-items: center;
	}
	.step {
		font-family: var(--mono);
		font-size: 0.8rem;
		overflow-wrap: anywhere;
	}
	.bars {
		display: grid;
		gap: 3px;
		border-left: 1px solid var(--line);
		padding-left: 2px;
	}
	.track {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 1.1rem;
	}
	.bar {
		display: flex;
		gap: 2px;
		height: 0.9rem;
		border-radius: 0 4px 4px 0;
		overflow: hidden;
		flex: none;
	}
	.bar[data-series='1'],
	.swatch[data-series='1'] {
		background: var(--series-1);
	}
	.bar[data-series='2'],
	.swatch[data-series='2'] {
		background: var(--series-2);
	}
	.bar.split {
		background: none;
	}
	.part {
		flex-basis: 0;
		min-width: 2px;
	}
	.part[data-kind='input'],
	.swatch[data-kind='input'] {
		background: var(--kind-input);
	}
	.part[data-kind='cache_write'],
	.swatch[data-kind='cache_write'] {
		background: var(--kind-cache_write);
	}
	.part[data-kind='cache_read'],
	.swatch[data-kind='cache_read'] {
		background: var(--kind-cache_read);
	}
	.part[data-kind='output'],
	.swatch[data-kind='output'] {
		background: var(--kind-output);
	}
	.value {
		font-size: 0.8rem;
		color: var(--ink-2);
		white-space: nowrap;
	}
</style>
