<!--
	The frame of every page (ADR-0178): a skip link, the bar with the mark, the depth the reader
	stands at — overview, process, run, origin — the theme, the control that stops all motion and
	signing out; the one navigation list beside the content, pinned from the design system's
	expanded width and a drawer below it. A destination that waits for the reader carries a mark,
	read from the surface's own lines. Colours, type and motion are the design system's tokens
	(ADR-0177). Signing out ends the reader's session on the instance (ADR-0119).
-->
<script lang="ts">
	import '../lib/generated/tokens.css';
	import '../app.css';
	import { onMount, type Snippet } from 'svelte';
	import { page } from '$app/state';
	import { surface, read } from '../lib/api';
	import { frame } from '../lib/frame.svelte';
	import { currentAdministrationKey, governanceLines } from '../lib/governance';
	import Icon from '../lib/Icon.svelte';
	import Mark from '../lib/Mark.svelte';
	import { motion } from '../lib/motion.svelte';
	import { BANDS, currentDestination, DESTINATIONS, waitingDestinations } from '../lib/navigation';
	import { operationLines, type OperationSummary } from '../lib/operation';
	import { forgetOldKey, signOut } from '../lib/session';
	import { apply, theme, THEMES } from '../lib/theme.svelte';

	let { children }: { children: Snippet } = $props();
	let open = $state(false);
	let waiting: Set<string> = $state(new Set());
	let main: HTMLElement | undefined = $state();

	onMount(() => {
		forgetOldKey();
		apply(theme.choice);
		return motion.listen();
	});

	const calm = $derived(motion.stoppedByReader || motion.reducedBySystem);
	$effect(() => {
		if (calm) document.documentElement.dataset.motion = 'reduced';
		else delete document.documentElement.dataset.motion;
	});

	/** The marks of what waits: read when the frame opens, and again on every return to Today. */
	async function readWaiting() {
		const base = surface(location.href);
		const [governs, operation] = await Promise.all([
			governanceLines(base, currentAdministrationKey()),
			read<OperationSummary>(base, 'operation')
		]);
		waiting = waitingDestinations(governs, operation.ok ? operationLines(operation.body) : []);
	}
	$effect(() => {
		if (page.route.id === '/') void readWaiting();
	});
	onMount(() => {
		if (page.route.id !== '/') void readWaiting();
	});

	// A new page closes the drawer.
	$effect(() => {
		void page.url.hash;
		open = false;
	});

	async function leave() {
		await signOut(surface(location.href));
		location.reload();
	}

	function skip() {
		main?.focus();
	}

	const current = $derived(currentDestination(page.route.id));
	const DEPTHS = ['Overview', 'Process', 'Run', 'Origin'] as const;
	const depth = $derived(
		page.route.id?.startsWith('/origins')
			? 3
			: page.route.id?.startsWith('/runs')
				? 2
				: page.route.id?.startsWith('/processes')
					? 1
					: page.route.id === '/'
						? 0
						: -1
	);
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && open && (open = false)} />

<button class="skip" type="button" onclick={skip}>Skip to the content</button>

<header class="bar">
	<button
		class="square menu"
		type="button"
		aria-expanded={open}
		aria-controls="destinations"
		onclick={() => (open = !open)}
	>
		<Icon name={open ? 'close' : 'menu'} />
		<span class="sr-only">{open ? 'Close the navigation' : 'Open the navigation'}</span>
	</button>
	<a class="home" href="#/">
		<Mark beat={frame.changes} still={calm} />
		<span class="word">taktus</span>
	</a>
	{#if depth >= 0}
		<nav class="depth" aria-label="Depth">
			{#each DEPTHS as name, i (name)}
				{#if i > 0}<span class="rail" class:done={i <= depth} aria-hidden="true"></span>{/if}
				{#if i === 0 && depth !== 0}
					<a class="stop done" href="#/">{name}</a>
				{:else}
					<span class="stop" class:done={i < depth} class:here={i === depth} aria-current={i === depth ? 'page' : undefined}
						>{name}</span>
				{/if}
			{/each}
		</nav>
	{:else}
		<span class="depth"></span>
	{/if}
	{#if frame.live !== null && page.route.id !== '/'}
		<p class="live" class:on={frame.live} aria-live="polite">
			<span class="pulse" aria-hidden="true"></span>{frame.live ? 'Live' : 'Reconnecting…'}
		</p>
	{/if}
	<div class="tools">
		<div class="segmented" role="group" aria-label="Theme">
			{#each THEMES as t (t.id)}
				<button type="button" aria-pressed={theme.choice === t.id} onclick={() => theme.choose(t.id)} title="{t.label} theme">
					<Icon name={t.id === 'system' ? 'system' : t.id === 'light' ? 'sun' : 'moon'} size={16} />
					<span class="sr-only">{t.label}</span>
				</button>
			{/each}
		</div>
		<button
			class="pill"
			type="button"
			aria-pressed={calm}
			disabled={motion.reducedBySystem}
			onclick={() => (motion.stoppedByReader = !motion.stoppedByReader)}
		>
			<Icon name="motion" size={16} />
			<span class="label">Stop motion{#if motion.reducedBySystem}{' '}(the system asks for it){/if}</span>
		</button>
		<button class="pill" type="button" onclick={leave}>
			<Icon name="leave" size={16} />
			<span class="label">Sign out</span>
		</button>
	</div>
</header>

<div class="frame">
	<nav id="destinations" class="side" class:open aria-label="Destinations">
		{#each BANDS as band (band.id)}
			<p class="band" id="band-{band.id}">{band.label}</p>
			<ul aria-labelledby="band-{band.id}">
				{#each DESTINATIONS.filter((d) => d.band === band.id) as d (d.id)}
					<li>
						<a href={d.href} aria-current={current === d.id ? 'page' : undefined} data-destination={d.id}>
							<Icon name={d.icon} />
							<span class="name">{d.label}</span>
							{#if waiting.has(d.id)}
								<span class="waits" aria-hidden="true"></span><span class="sr-only">, needs a look</span>
							{/if}
						</a>
					</li>
				{/each}
			</ul>
		{/each}
	</nav>
	{#if open}
		<button class="scrim" type="button" tabindex="-1" aria-label="Close the navigation" onclick={() => (open = false)}></button>
	{/if}
	<main id="main" tabindex="-1" bind:this={main}>
		{@render children()}
	</main>
</div>

<style>
	.skip {
		min-height: 0;
		position: fixed;
		inset-block-start: var(--sp-100);
		inset-inline-start: var(--sp-100);
		z-index: var(--z-toast);
		transform: translateY(-200%);
		padding: var(--sp-100) var(--sp-200);
		border-radius: var(--r-md);
		border: none;
		background: var(--accent-primary);
		color: var(--text-inverse);
	}
	.skip:focus-visible {
		transform: none;
	}

	/* The bar: a plane of the surface above the canvas, a hairline beneath, no elevation. */
	.bar {
		position: sticky;
		inset-block-start: 0;
		z-index: var(--z-sticky);
		display: flex;
		align-items: center;
		gap: var(--sp-200);
		height: var(--layout-appbar-height);
		padding: 0 var(--sp-200);
		background: var(--bg-glass);
		backdrop-filter: saturate(1.4) blur(14px);
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
	}
	@supports not (backdrop-filter: blur(1px)) {
		.bar {
			background: var(--bg-surface);
		}
	}
	.home {
		display: flex;
		align-items: center;
		gap: var(--sp-100);
		text-decoration: none;
		flex: none;
	}
	.word {
		font-family: var(--font-display);
		font-weight: var(--fw-bold);
		font-size: var(--fs-400);
		letter-spacing: -0.03em;
		color: var(--text-brand);
	}
	.square,
	.pill,
	.segmented button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--sp-050);
		min-height: var(--density-control-sm-min);
		border: var(--bw-hairline) solid var(--border-subtle);
		background: var(--bg-surface);
		color: var(--text-primary);
		border-radius: var(--r-full);
		font-size: var(--fs-075);
		font-weight: var(--fw-medium);
		transition: background-color var(--motion-state-duration) var(--motion-state-easing);
	}
	.square {
		padding: 0;
		width: var(--density-control-sm-min);
		border-radius: var(--r-md);
	}
	.pill {
		padding: 0 var(--sp-150);
	}
	.square:hover,
	.pill:hover,
	.segmented button:hover {
		background: var(--bg-surface-hover);
	}
	.pill[aria-pressed='true'] {
		background: var(--text-primary);
		color: var(--text-inverse);
		border-color: var(--text-primary);
	}
	.segmented {
		display: inline-flex;
		padding: var(--sp-025);
		gap: var(--sp-025);
		background: var(--bg-recess);
		border-radius: var(--r-full);
	}
	.segmented button {
		padding: 0;
		width: var(--sp-400);
		min-height: var(--sp-300);
		border-color: transparent;
		background: transparent;
	}
	.segmented button[aria-pressed='true'] {
		background: var(--bg-surface);
		box-shadow: var(--shadow-raised);
		color: var(--text-brand);
	}
	.tools {
		display: flex;
		align-items: center;
		gap: var(--sp-100);
		flex: none;
	}

	/* The depth: four stops on a rail; the one the reader stands at is filled. */
	.depth {
		display: flex;
		align-items: center;
		flex: 1;
		min-width: 0;
		overflow: hidden;
		font-size: var(--fs-075);
		color: var(--text-subtle);
	}
	.stop {
		display: flex;
		align-items: center;
		gap: var(--sp-050);
		white-space: nowrap;
		text-decoration: none;
	}
	.stop::before {
		content: '';
		width: 8px;
		height: 8px;
		border-radius: var(--r-full);
		border: var(--bw-thick) solid currentColor;
		flex: none;
	}
	.stop.done {
		color: var(--text-secondary);
	}
	.stop.done::before {
		background: currentColor;
	}
	.stop.here {
		color: var(--text-brand);
		font-weight: var(--fw-semibold);
	}
	.stop.here::before {
		background: var(--accent-primary);
		border-color: var(--accent-primary);
		box-shadow: 0 0 0 3px var(--accent-primary-subtle);
	}
	.rail {
		width: var(--sp-300);
		height: var(--bw-thick);
		margin: 0 var(--sp-100);
		background: var(--border-subtle);
		border-radius: var(--r-full);
		flex: none;
	}
	.rail.done {
		background: linear-gradient(to right, var(--text-secondary), var(--accent-primary));
	}

	/* The live state of the page's stream. */
	.live {
		display: flex;
		align-items: center;
		gap: var(--sp-050);
		margin: 0;
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
		flex: none;
	}
	.live.on {
		color: var(--text-success);
	}
	.pulse {
		width: 8px;
		height: 8px;
		border-radius: var(--r-full);
		border: var(--bw-thick) solid currentColor;
	}
	.live.on .pulse {
		background: currentColor;
	}

	/* The frame: the navigation column beside the content. */
	.frame {
		display: grid;
		grid-template-columns: var(--layout-sidenav-width) minmax(0, 1fr);
		min-height: calc(100vh - var(--layout-appbar-height));
	}
	.side {
		position: sticky;
		inset-block-start: var(--layout-appbar-height);
		align-self: start;
		height: calc(100vh - var(--layout-appbar-height));
		overflow-y: auto;
		padding: var(--sp-200) var(--sp-150) var(--sp-400);
		border-inline-end: var(--bw-hairline) solid var(--border-subtle);
		background: color-mix(in srgb, var(--bg-surface) 55%, transparent);
	}
	.band {
		margin: var(--sp-250) var(--sp-150) var(--sp-050);
		font-size: var(--fs-050);
		font-weight: var(--fw-semibold);
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-subtle);
	}
	.band:first-child {
		margin-top: 0;
	}
	.side ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: var(--sp-025);
	}
	.side a {
		position: relative;
		display: flex;
		align-items: center;
		gap: var(--sp-150);
		min-height: var(--density-control-md-min);
		padding: 0 var(--sp-150);
		border-radius: var(--r-md);
		text-decoration: none;
		font-size: var(--fs-100);
		font-weight: var(--fw-medium);
		color: var(--text-secondary);
		transition: background-color var(--motion-state-duration) var(--motion-state-easing);
	}
	.side a:hover {
		background: var(--bg-surface-hover);
		color: var(--text-primary);
	}
	.side a[aria-current='page'] {
		background: var(--accent-primary-subtle);
		color: var(--text-brand);
		font-weight: var(--fw-semibold);
	}
	.side a[aria-current='page']::before {
		content: '';
		position: absolute;
		inset-inline-start: calc(-1 * var(--sp-150));
		inset-block: var(--sp-100);
		width: 3px;
		border-radius: var(--r-full);
		background: var(--accent-primary);
	}
	.name {
		flex: 1;
	}
	/* Something waits for the reader: a filled mark, said in words to a screen reader. */
	.waits {
		width: 8px;
		height: 8px;
		border-radius: var(--r-full);
		background: var(--accent-primary);
		box-shadow: 0 0 0 3px var(--accent-primary-subtle);
	}
	main {
		min-width: 0;
		width: 100%;
		max-width: var(--layout-content-max);
		padding: var(--sp-500) var(--sp-600) var(--sp-1000);
	}
	main:focus {
		outline: none;
	}
	.scrim {
		display: none;
	}
	.menu {
		display: none;
	}

	/* Below the expanded width the column is a drawer the bar's menu opens. */
	@media (max-width: 904px) {
		.menu {
			display: inline-flex;
		}
		.frame {
			grid-template-columns: minmax(0, 1fr);
		}
		.side {
			position: fixed;
			inset-block: var(--layout-appbar-height) 0;
			inset-inline-start: 0;
			z-index: var(--z-overlay);
			width: min(var(--layout-sidenav-width), 85vw);
			height: auto;
			background: var(--bg-raised);
			box-shadow: var(--shadow-overlay);
			transform: translateX(-105%);
			visibility: hidden;
			transition:
				transform var(--motion-exit-duration) var(--motion-exit-easing),
				visibility var(--dur-instant) linear var(--motion-exit-duration);
		}
		.side.open {
			transform: none;
			visibility: visible;
			transition: transform var(--motion-entrance-duration) var(--motion-entrance-easing);
		}
		.scrim {
			display: block;
			position: fixed;
			inset: var(--layout-appbar-height) 0 0 0;
			z-index: calc(var(--z-overlay) - 1);
			border: none;
			background: var(--bg-scrim);
		}
		main {
			padding: var(--sp-300) var(--sp-200) var(--sp-800);
		}
		.rail,
		.stop:not(.here) {
			display: none;
		}
		.label {
			display: none;
		}
		.bar {
			gap: var(--sp-100);
			padding: 0 var(--sp-100);
		}
		.tools {
			margin-inline-start: auto;
		}
	}
	@media (max-width: 420px) {
		.segmented {
			display: none;
		}
	}
</style>
