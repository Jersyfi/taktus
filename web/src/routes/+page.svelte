<!--
	Today (ADR-0322 §4): the pulse card first — what waits for the reader in its first row, the
	overview's sentence, the live state and the Takt of the last 60 minutes — then the glance strip
	of counts, the waits (at most five, one list), what runs now, what just happened, and the
	processes drawn as one body. A tenant without a process sees the way to its first process before
	anything else (UC-10.4). Everything is read through `todayData.ts` and drawn from the frame's
	one stream of the tenant (ADR-0323): the page opens no stream of its own, and reads again on
	every change.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { failed, surface } from '../lib/api';
	import { changeLine, changeTime } from '../lib/changes';
	import { display } from '../lib/display.svelte';
	import DisplaySwitch from '../lib/DisplaySwitch.svelte';
	import EmptyState from '../lib/EmptyState.svelte';
	import ErrorState from '../lib/ErrorState.svelte';
	import { frame } from '../lib/frame.svelte';
	import { currentAdministrationKey } from '../lib/governance';
	import GovernanceLines from '../lib/GovernanceLines.svelte';
	import Glyph from '../lib/Glyph.svelte';
	import { galleryLink, runLink } from '../lib/links';
	import { Rereader } from '../lib/live';
	import { chosen, motion } from '../lib/motion.svelte';
	import OverviewView from '../lib/OverviewView.svelte';
	import SignInForm from '../lib/SignInForm.svelte';
	import Skeleton from '../lib/Skeleton.svelte';
	import TaktStrip from '../lib/TaktStrip.svelte';
	import { merged, minutes, recentChanges, taktLine } from '../lib/takt';
	import { glance, waitsLine } from '../lib/today';
	import { markOf } from '../lib/navigation';
	import { KIND_WORD, readToday, WAITS_ON_TODAY, type TodayData } from '../lib/todayData';
	import type { Change, Problem } from '../lib/types';

	const PAGE = 'today';
	let signedIn = $state(true);
	let today = $state<TodayData | null>(null);
	let problem = $state<Problem | null>(null);
	/** The last hour as the surface kept it; null where it does not serve it. */
	let history = $state<Change[] | null>(null);
	let now = $state(Date.now());
	/** How many changes had arrived when the page opened: only later ones are new here. */
	let openedAt = frame.changes;

	const base = () => surface(location.href);
	const rereader = new Rereader(async () => {
		const found = await readToday(base(), currentAdministrationKey());
		if (found.ok) {
			today = found.today;
			problem = null;
		} else if (found.problem.status === 401) signedIn = false;
		else problem = found.problem;
	});

	onMount(() => {
		void rereader.request();
		void recentChanges(base()).then((found) => (history = found));
		const stop = frame.subscribe(() => void rereader.request());
		const timer = setInterval(() => (now = Date.now()), 30_000);
		return () => {
			stop();
			clearInterval(timer);
		};
	});

	function signedInAgain() {
		signedIn = true;
		void rereader.request();
	}

	const mode = $derived(display.of(PAGE));
	const arrived = $derived(frame.recent.slice(Math.max(0, frame.recent.length - (frame.changes - openedAt))));
	const changes = $derived(merged(history ?? [], frame.recent));
	const drawn = $derived(minutes(changes, Math.max(now, ...arrived.map((c) => Date.parse(c.recorded_at)).filter((t) => !Number.isNaN(t)))));
	const newest = $derived(arrived.at(-1));
	const arrivedAt = $derived(newest ? Math.floor(Date.parse(newest.recorded_at) / 60_000) * 60_000 : null);
	const justHappened = $derived(changes.slice(-10).reverse());
	const empty = $derived(today !== null && today.overview.areas.every((area) => area.processes.length === 0));
	const running = $derived(today ? today.overview.areas.flatMap((a) => a.processes.flatMap((p) => (p.running ?? []).map((s) => ({ ...s, process: p.name })))) : []);
	const tiles = $derived(today ? glance(today.counts) : []);
	const shownWaits = $derived(today ? today.waits.slice(0, WAITS_ON_TODAY) : []);
	const governs = $derived(today ? today.lines.filter((l) => !l.waiting && l.kind !== 'requests' && l.kind !== 'needs') : []);
	const idle = $derived(drawn.every((m) => m.count === 0));
</script>

{#if !signedIn}
	<SignInForm onSignedIn={signedInAgain} />
{:else if today}
	{#if empty}
		<!-- A tenant with no process yet starts from the gallery (UC-10.4, ADR-0136 §5). -->
		<section class="first" data-first-process aria-labelledby="first-title">
			<h2 id="first-title">Your first process</h2>
			<ol class="path">
				<li><strong>Choose</strong> a process from the gallery, for a family, a club or a small business.</li>
				<li><strong>Rehearse</strong> it: it runs, and acts on nothing outside Taktus.</li>
				<li><strong>Commission</strong> it once the rehearsal shows what it does.</li>
			</ol>
			<p>
				Nothing runs here yet. <a class="go" href={galleryLink()}>Choose a first process from the gallery</a>, rehearse it,
				and see what it does before it does anything for real.
			</p>
		</section>
	{/if}

	<!-- The pulse card: what waits first, then the sentence, the live state and the Takt. -->
	<section class="pulse" class:idle aria-labelledby="today-title" data-pulse>
		<div class="first-row">
			<a class="waiting-tile" href="#/waits" data-tile="waiting_for_you" class:some={(today.counts.waiting_for_you ?? 0) > 0}>
				<span class="figure">{today.counts.waiting_for_you ?? '–'}</span>
				<span class="what">{waitsLine(today.counts.waiting_for_you)}</span>
			</a>
			<div class="said">
				<p class="eyebrow">Today</p>
				<h1 id="today-title">{today.overview.summary}</h1>
				<p class="state" class:on={frame.live} data-live={frame.live ? 'on' : 'off'}>
					<span class="dot" aria-hidden="true"></span>{frame.live === null ? 'Not following' : frame.live ? 'Live' : 'Reconnecting'}
				</p>
			</div>
		</div>
		<div class="takt">
			<TaktStrip {drawn} arrival={frame.changes - openedAt} {arrivedAt} still={!motion.allowed} />
			<div class="axis" aria-hidden="true"><span>60 min ago</span><span>now</span></div>
			<p class="takt-line" data-takt-line>
				{taktLine(drawn, changes, now)}
				{#if history === null}<span class="note"> The surface keeps no history of the last hour here; the strip shows what arrived since you opened Taktus.</span>{/if}
			</p>
		</div>
	</section>

	{#if tiles.length || today.operation}
		<ul class="glance" aria-label="At a glance">
			{#each tiles as tile (tile.key)}
				<li data-tile={tile.key} class:alert={tile.alert}>
					<a href={tile.href}>
						<span class="figure">{tile.value}</span>
						<span class="what">{tile.label}</span>
					</a>
				</li>
			{/each}
			{#if today.operation}
				<li data-tile="operation" class="wide" class:alert={today.marks.some((m) => markOf(m) === 'operation')}>
					<a href="#/incidents">
						<span class="what">Operation</span>
						<span class="said">{today.operation}</span>
					</a>
				</li>
			{/if}
		</ul>
	{/if}

	{#if today.failed.length}
		<ErrorState what={`Part of Today (${today.failed.join(', ')})`} problem={{ status: 0, title: '', detail: 'A read failed; what it shows is left out, not shown as nothing.' }} onRetry={() => void rereader.request()} />
	{/if}

	<section class="block" aria-labelledby="waits-title">
		<div class="head">
			<h2 id="waits-title">Waits for you</h2>
			{#if today.waits_total > shownWaits.length}<a href="#/waits">All {today.waits_total}</a>{/if}
		</div>
		{#if shownWaits.length}
			<ol class="waits" data-waits>
				{#each shownWaits as w (w.id)}
					<li data-wait={w.id} class:overdue={w.overdue}>
						<a href={w.href}>
							<span class="title">{w.title}</span>
							<span class="meta">{KIND_WORD[w.kind] ?? 'Report'} · {w.id}{w.due ? ` · needed by ${w.due}` : ''}{w.overdue ? ' · past its date' : ''}</span>
						</a>
					</li>
				{/each}
			</ol>
		{:else if today.counts.waiting_for_you === 0}
			<EmptyState title="Nothing waits for you." />
		{:else}
			<p class="meta">What waits for you could not be read.</p>
		{/if}
	</section>

	<div class="pair">
		<section class="block" aria-labelledby="running-title">
			<h2 id="running-title">Now running</h2>
			{#if running.length}
				<ul class="rows">
					{#each running as step (`${step.run}/${step.step}`)}
						<li>
							<Glyph glyph={chosen(step.drawn, motion.allowed)} size={22} />
							<a href={runLink(step.run)}>{step.step}</a>
							<span class="meta">{step.process} · {step.run}</span>
						</li>
					{/each}
				</ul>
			{:else}
				<EmptyState title="Nothing runs right now." />
			{/if}
		</section>

		<section class="block" aria-labelledby="happened-title">
			<h2 id="happened-title">Just happened</h2>
			{#if justHappened.length}
				<ol class="rows" data-just-happened>
					{#each justHappened as c (c.position)}
						<li>
							<time datetime={c.recorded_at}>{changeTime(c)}</time>
							<a href={runLink(c.run)}>{changeLine(c)}</a>
						</li>
					{/each}
				</ol>
			{:else}
				<EmptyState title={history === null ? "No change has arrived since you opened Taktus." : "No change recorded in the last hour."} />
			{/if}
		</section>
	</div>

	<section class="block" aria-labelledby="runs-title">
		<div class="head">
			<h2 id="runs-title">What runs</h2>
			<DisplaySwitch page={PAGE} />
		</div>
		<OverviewView level={today.overview} motionAllowed={motion.allowed} {mode} headed={false} exactness={false} />
	</section>

	<!-- What governs the work and waits for nothing; decision requests and needs are the Waits above. -->
	{#if governs.length}
		<GovernanceLines lines={governs} />
	{/if}
{:else if problem && failed(problem)}
	<ErrorState what="Today" {problem} onRetry={() => void rereader.request()} />
{:else if problem}
	<p role="alert">{problem.detail || problem.title}</p>
{:else}
	<Skeleton label="Reading Today…" lines={4} />
{/if}

<style>
	/* The pulse card: the first thing on the page, a plane raised above the canvas. */
	.pulse {
		display: grid;
		gap: var(--sp-250);
		padding: var(--sp-300);
		border-radius: var(--r-2xl);
		background:
			radial-gradient(80% 120% at 100% 0%, var(--accent-primary-subtle), transparent 70%),
			var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		box-shadow: var(--shadow-raised);
	}
	.first-row {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: var(--sp-300);
		align-items: start;
	}
	.waiting-tile {
		display: grid;
		justify-items: start;
		gap: var(--sp-050);
		min-width: 9rem;
		padding: var(--sp-200) var(--sp-250);
		border-radius: var(--r-xl);
		background: var(--bg-recess);
		text-decoration: none;
	}
	.waiting-tile.some {
		background: var(--accent-primary);
		color: var(--text-inverse);
		box-shadow: var(--shadow-glow);
	}
	.waiting-tile .figure {
		font-family: var(--font-display);
		font-size: var(--fs-700);
		font-weight: var(--fw-bold);
		line-height: var(--lh-tight);
	}
	.waiting-tile .what {
		font-size: var(--fs-090);
		font-weight: var(--fw-semibold);
	}
	.said h1 {
		font-size: clamp(var(--fs-450), 3.6vw, var(--fs-600));
		margin-bottom: var(--sp-100);
	}
	.state {
		display: inline-flex;
		align-items: center;
		gap: var(--sp-050);
		margin: 0;
		padding: var(--sp-025) var(--sp-150);
		border-radius: var(--r-full);
		background: var(--status-neutral-surface);
		color: var(--status-neutral-text);
		font-weight: var(--fw-semibold);
		font-size: var(--fs-075);
	}
	.state.on {
		background: var(--status-success-surface);
		color: var(--status-success-text);
	}
	.dot {
		width: var(--sp-100);
		height: var(--sp-100);
		border-radius: var(--r-full);
		border: var(--bw-thick) solid currentColor;
	}
	.state.on .dot {
		background: currentColor;
	}
	.takt {
		display: grid;
		gap: var(--sp-050);
	}
	.axis {
		display: flex;
		justify-content: space-between;
		font-size: var(--fs-065);
		color: var(--text-subtle);
	}
	.takt-line {
		margin: 0;
		font-size: var(--fs-090);
		color: var(--text-secondary);
	}
	.note {
		color: var(--text-subtle);
	}

	/* The glance strip: one tile per count the surface made. */
	.glance {
		list-style: none;
		padding: 0;
		margin: var(--sp-250) 0 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 9rem), 1fr));
		gap: var(--sp-150);
	}
	.glance a {
		display: grid;
		gap: var(--sp-025);
		padding: var(--sp-150) var(--sp-200);
		border-radius: var(--r-lg);
		background: var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		text-decoration: none;
		height: 100%;
	}
	.glance .figure {
		font-family: var(--font-display);
		font-size: var(--fs-500);
		font-weight: var(--fw-bold);
	}
	.glance .what {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
	.glance .said {
		font-weight: var(--fw-semibold);
	}
	.glance .wide {
		grid-column: span 2;
	}
	.glance .alert a {
		border-color: var(--status-danger-border);
		border-inline-start-width: var(--bw-thick);
	}

	.block {
		margin-top: var(--sp-400);
	}
	.head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--sp-200);
		flex-wrap: wrap;
	}
	.pair {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
		column-gap: var(--sp-400);
	}
	.waits,
	.rows {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: var(--sp-100);
	}
	.waits a {
		display: grid;
		gap: var(--sp-025);
		padding: var(--sp-150) var(--sp-200);
		border-radius: var(--r-lg);
		background: var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-inline-start: var(--bw-thick) solid var(--accent-primary);
		text-decoration: none;
	}
	.waits .overdue a {
		border-inline-start-color: var(--family-alert);
	}
	.waits .title {
		font-weight: var(--fw-semibold);
	}
	.meta {
		font-size: var(--fs-075);
		color: var(--text-secondary);
	}
	.rows li {
		display: flex;
		align-items: center;
		gap: var(--sp-100);
		min-width: 0;
		font-size: var(--fs-090);
	}
	.rows time {
		flex: none;
		font-family: var(--font-mono);
		font-size: var(--fs-075);
		color: var(--text-subtle);
	}

	.first {
		margin: 0 0 var(--sp-300);
		padding: var(--sp-300);
		border-radius: var(--r-2xl);
		background:
			radial-gradient(90% 120% at 100% 0%, var(--accent-primary-subtle), transparent 70%),
			var(--bg-surface);
		border: var(--bw-hairline) solid var(--border-subtle);
		box-shadow: var(--shadow-raised);
	}
	.first h2 {
		margin-top: 0;
	}
	.path {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
		gap: var(--sp-200);
		padding: 0;
		margin: 0 0 var(--sp-200);
		list-style: none;
		counter-reset: step;
	}
	.path li {
		counter-increment: step;
		color: var(--text-secondary);
	}
	.path li::before {
		content: counter(step);
		display: grid;
		place-items: center;
		width: var(--sp-400);
		height: var(--sp-400);
		margin-bottom: var(--sp-100);
		border-radius: var(--r-full);
		background: var(--accent-primary);
		color: var(--text-inverse);
		font-weight: var(--fw-bold);
	}
	.path strong {
		color: var(--text-primary);
	}
	.go {
		display: inline-block;
		font-weight: var(--fw-semibold);
	}

	@media (max-width: 599px) {
		.first-row {
			grid-template-columns: minmax(0, 1fr);
		}
		.waiting-tile {
			grid-template-columns: auto 1fr;
			align-items: center;
			column-gap: var(--sp-150);
			width: 100%;
		}
		.waiting-tile .figure {
			font-size: var(--fs-600);
		}
	}
</style>
