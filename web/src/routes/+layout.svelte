<!--
	The frame of every page (ADR-0178, ADR-0321): a skip link, the bar with the mark, the trail to
	where the reader stands, the live state and the account menu; the one navigation list in five
	bands beside the content from the expanded width, a drawer below it, and a bottom bar on a
	phone. The frame holds one stream of the tenant's changes (ADR-0323): the mark beats on it on
	every page, and a change of a decision request reads the marks of what waits again. Colours,
	type and motion are the design system's tokens (ADR-0177). Signing out ends the reader's session
	on the instance (ADR-0119).
-->
<script lang="ts">
	import '../lib/generated/tokens.css';
	import '../app.css';
	import { onMount, type Snippet } from 'svelte';
	import { page } from '$app/state';
	import { surface } from '../lib/api';
	import { display, type Display } from '../lib/display.svelte';
	import { frame } from '../lib/frame.svelte';
	import Icon from '../lib/Icon.svelte';
	import Mark from '../lib/Mark.svelte';
	import { motion } from '../lib/motion.svelte';
	import { BANDS, BOTTOM, currentBottom, currentDestination, DESTINATIONS, markOf, TABS, trail } from '../lib/navigation';
	import { forgetOldKey, signOut } from '../lib/session';
	import { apply, theme, THEMES } from '../lib/theme.svelte';
	import { readToday } from '../lib/todayData';

	let { children }: { children: Snippet } = $props();
	let open = $state(false);
	let account = $state(false);
	let waiting: Set<string> = $state(new Set());
	let main: HTMLElement | undefined = $state();
	let phone = $state(false);

	onMount(() => {
		forgetOldKey();
		apply(theme.choice);
		frame.open(surface(location.href));
		// The page's own read goes first; the marks follow it (on Today they share its reads).
		const marks = setTimeout(() => void readWaiting(), page.route.id === '/' ? 0 : 1500);
		// A decision request raised or answered anywhere moves the marks (ADR-0321 §5).
		const stop = frame.subscribe((event) => {
			if (event.kind === 'change' && event.change.decision_request) void readWaiting();
		});
		const query = typeof matchMedia === 'function' ? matchMedia('(max-width: 599px)') : null;
		const sized = () => (phone = query?.matches ?? false);
		sized();
		query?.addEventListener('change', sized);
		const quiet = motion.listen();
		return () => {
			clearTimeout(marks);
			stop();
			quiet();
			query?.removeEventListener('change', sized);
		};
	});

	const calm = $derived(motion.stoppedByReader || motion.reducedBySystem);
	$effect(() => {
		if (calm) document.documentElement.dataset.motion = 'reduced';
		else delete document.documentElement.dataset.motion;
	});
	// A phone carries the design system's spacious density.
	$effect(() => {
		if (phone) document.documentElement.dataset.density = 'spacious';
		else delete document.documentElement.dataset.density;
	});

	/** The marks of what waits, from the reads Today shares (ADR-0323 §4). */
	async function readWaiting() {
		const found = await readToday(surface(location.href));
		if (found.ok) waiting = new Set(found.today.marks.map(markOf));
	}
	// A return to Today reads them too: the reads are shared, so this costs nothing twice.
	$effect(() => {
		if (page.route.id === '/') void readWaiting();
	});

	// A new page closes the drawer and the menu.
	$effect(() => {
		void page.url.hash;
		open = false;
		account = false;
	});

	async function leave() {
		await signOut(surface(location.href));
		location.reload();
	}

	function skip() {
		main?.focus();
	}

	const current = $derived(currentDestination(page.route.id));
	const bottom = $derived(currentBottom(page.route.id));
	const steps = $derived(trail(page.route.id, page.params as Record<string, string | undefined>));
	const DISPLAYS: { id: Display; label: string }[] = [
		{ id: 'picture', label: 'Picture' },
		{ id: 'text', label: 'Text' }
	];
</script>

<svelte:window
	onkeydown={(e) => {
		if (e.key !== 'Escape') return;
		open = false;
		account = false;
	}}
/>

<button class="skip" type="button" onclick={skip}>Skip to the content</button>

{#snippet accountGroup()}
	<div class="group" role="group" aria-label="Theme">
		<p class="label">Theme</p>
		<div class="segmented">
			{#each THEMES as t (t.id)}
				<button type="button" aria-pressed={theme.choice === t.id} onclick={() => theme.choose(t.id)}>
					<Icon name={t.id === 'system' ? 'system' : t.id === 'light' ? 'sun' : 'moon'} size={16} />
					<span>{t.label}</span>
				</button>
			{/each}
		</div>
	</div>
	<div class="group" role="group" aria-label="Show pages as">
		<p class="label">Show pages as</p>
		<div class="segmented">
			{#each DISPLAYS as d (d.id)}
				<button type="button" aria-pressed={display.fallback === d.id} onclick={() => display.setDefault(d.id)}>
					<Icon name={d.id} size={16} />
					<span>{d.label}</span>
				</button>
			{/each}
		</div>
	</div>
	<button
		class="row"
		type="button"
		aria-pressed={calm}
		disabled={motion.reducedBySystem}
		title={motion.reducedBySystem ? 'Your system asks for reduced motion' : undefined}
		onclick={() => (motion.stoppedByReader = !motion.stoppedByReader)}
	>
		<Icon name="motion" size={16} />
		<span>Reduce motion</span>
	</button>
	<button class="row" type="button" onclick={leave}>
		<Icon name="leave" size={16} />
		<span>Sign out</span>
	</button>
{/snippet}

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
		<span class="sr-only">, Today</span>
	</a>
	{#if steps.length}
		<nav class="trail" aria-label="Where you are">
			<ol>
				{#each steps as step, i (i)}
					<li>
						{#if step.href}<a href={step.href}>{step.label}</a>{:else}<span aria-current="page">{step.label}</span>{/if}
					</li>
				{/each}
			</ol>
		</nav>
	{:else}
		<span class="trail"></span>
	{/if}
	{#if frame.live !== null}
		<p class="live" class:on={frame.live} data-live={frame.live ? 'on' : 'off'}>
			<span class="dot" aria-hidden="true"></span><span class="said">{frame.live ? 'Live' : 'Reconnecting'}</span>
		</p>
		<!-- Said once when the connection opens or is lost, never at each change (ADR-0322 §3). -->
		<p class="sr-only" aria-live="polite">{frame.live ? 'Live.' : 'Reconnecting.'}</p>
	{/if}
	<div class="account">
		<button
			class="square"
			type="button"
			aria-expanded={account}
			aria-controls="account-menu"
			onclick={() => (account = !account)}
		>
			<Icon name="account" />
			<span class="sr-only">Account and display</span>
		</button>
		{#if account}
			<div id="account-menu" class="menu-panel">
				{@render accountGroup()}
			</div>
		{/if}
	</div>
</header>

<div class="frame">
	<nav id="destinations" class="side" class:open aria-label="Destinations">
		{#each BANDS as band (band.id)}
			{@const first = DESTINATIONS.filter((d) => d.band === band.id && !d.more)}
			{@const folded = DESTINATIONS.filter((d) => d.band === band.id && d.more)}
			<p class="band" id="band-{band.id}">{band.label}</p>
			<ul aria-labelledby="band-{band.id}">
				{#each first as d (d.id)}
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
			{#if folded.length}
				<details class="fold" open={folded.some((d) => d.id === current) || undefined}>
					<summary><Icon name="more" size={16} /><span>More</span></summary>
					<ul>
						{#each folded as d (d.id)}
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
				</details>
			{/if}
		{/each}
		{#if phone}
			<div class="sheet-account">
				<p class="band">Account</p>
				{@render accountGroup()}
			</div>
		{/if}
	</nav>
	{#if open || account}
		<button
			class="scrim"
			class:clear={!open}
			type="button"
			tabindex="-1"
			aria-label="Close"
			onclick={() => {
				open = false;
				account = false;
			}}
		></button>
	{/if}
	<main id="main" tabindex="-1" bind:this={main}>
		{#if current && TABS[current]}
			<!-- Pages that answer one question from several sides, as tabs (ADR-0321 §1). -->
			<nav class="tabs" aria-label={DESTINATIONS.find((d) => d.id === current)?.label}>
				{#each TABS[current] as t (t.route)}
					<a href={t.href} aria-current={page.route.id === t.route ? 'page' : undefined}>{t.label}</a>
				{/each}
			</nav>
		{/if}
		{@render children()}
	</main>
</div>

<nav class="bottom" aria-label="Main">
	{#each BOTTOM as b (b.id)}
		<a href={b.href} aria-current={bottom === b.id && !open ? 'page' : undefined}>
			<Icon name={b.icon} />
			<span>{b.label}</span>
			{#if b.id === 'waits' && (waiting.has('requests') || waiting.has('needs'))}
				<span class="waits" aria-hidden="true"></span><span class="sr-only">, something waits</span>
			{/if}
		</a>
	{/each}
	<button type="button" aria-expanded={open} aria-controls="destinations" aria-current={open ? 'page' : undefined} onclick={() => (open = !open)}>
		<Icon name={open ? 'close' : 'menu'} />
		<span>Menu</span>
	</button>
</nav>

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
	.square {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		width: var(--density-control-sm-min);
		min-height: var(--density-control-sm-min);
		border: var(--bw-hairline) solid var(--border-subtle);
		border-radius: var(--r-md);
		background: var(--bg-surface);
	}
	.square[aria-expanded='true'] {
		background: var(--bg-surface-hover);
	}

	/* The trail: every step but the last a link (ADR-0321 §3). */
	.trail {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		font-size: var(--fs-090);
		color: var(--text-secondary);
	}
	.trail ol {
		display: flex;
		align-items: center;
		gap: var(--sp-100);
		list-style: none;
		margin: 0;
		padding: 0;
		white-space: nowrap;
	}
	.trail li {
		display: flex;
		align-items: center;
		gap: var(--sp-100);
		min-width: 0;
	}
	.trail li + li::before {
		content: '›';
		color: var(--text-subtle);
	}
	.trail span {
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--text-primary);
		font-weight: var(--fw-semibold);
	}

	/* The live state of the frame's stream. */
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
	.dot {
		width: var(--sp-100);
		height: var(--sp-100);
		border-radius: var(--r-full);
		border: var(--bw-thick) solid currentColor;
	}
	.live.on .dot {
		background: currentColor;
	}

	/* The account menu: theme, how pages show, motion and signing out. */
	.account {
		position: relative;
		flex: none;
	}
	.menu-panel {
		position: absolute;
		inset-inline-end: 0;
		inset-block-start: calc(100% + var(--sp-100));
		z-index: var(--z-overlay);
		display: grid;
		gap: var(--sp-150);
		width: max-content;
		min-width: 16rem;
		padding: var(--sp-200);
		border-radius: var(--r-lg);
		background: var(--bg-raised);
		border: var(--bw-hairline) solid var(--border-subtle);
		box-shadow: var(--shadow-overlay);
	}
	.group {
		display: grid;
		gap: var(--sp-050);
	}
	.label {
		margin: 0;
		font-size: var(--fs-075);
		font-weight: var(--fw-semibold);
		color: var(--text-subtle);
	}
	.segmented {
		display: inline-flex;
		padding: var(--sp-025);
		gap: var(--sp-025);
		background: var(--bg-recess);
		border-radius: var(--r-full);
	}
	.segmented button {
		gap: var(--sp-050);
		min-height: var(--density-control-sm-min);
		padding: 0 var(--sp-150);
		border: none;
		border-radius: var(--r-full);
		background: transparent;
		font-size: var(--fs-075);
	}
	.segmented button[aria-pressed='true'] {
		background: var(--bg-surface);
		box-shadow: var(--shadow-raised);
		color: var(--text-brand);
	}
	.row {
		justify-content: flex-start;
		gap: var(--sp-100);
		font-size: var(--fs-090);
	}
	.row[aria-pressed='true'] {
		background: var(--text-primary);
		color: var(--text-inverse);
		border-color: var(--text-primary);
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
	.side a,
	.fold summary {
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
	.fold summary {
		list-style: none;
		min-height: var(--density-control-sm-min);
		font-size: var(--fs-090);
		color: var(--text-subtle);
	}
	.fold summary::-webkit-details-marker {
		display: none;
	}
	.fold[open] summary {
		color: var(--text-secondary);
	}
	.side a:hover,
	.fold summary:hover {
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
		width: var(--bw-thick);
		border-radius: var(--r-full);
		background: var(--accent-primary);
	}
	.name {
		flex: 1;
	}
	/* Something waits for the reader: a filled mark, said in words to a screen reader. */
	.waits {
		width: var(--sp-100);
		height: var(--sp-100);
		border-radius: var(--r-full);
		background: var(--accent-primary);
		box-shadow: 0 0 0 3px var(--accent-primary-subtle);
	}
	.sheet-account {
		display: grid;
		gap: var(--sp-150);
		padding: 0 var(--sp-150);
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
	.tabs {
		display: flex;
		gap: var(--sp-050);
		margin-bottom: var(--sp-300);
		border-bottom: var(--bw-hairline) solid var(--border-subtle);
		overflow-x: auto;
	}
	.tabs a {
		padding: var(--sp-100) var(--sp-150);
		margin-bottom: calc(-1 * var(--bw-hairline));
		border-bottom: var(--bw-thick) solid transparent;
		text-decoration: none;
		white-space: nowrap;
		font-size: var(--fs-100);
		font-weight: var(--fw-medium);
		color: var(--text-secondary);
	}
	.tabs a[aria-current='page'] {
		border-bottom-color: var(--accent-primary);
		color: var(--text-brand);
		font-weight: var(--fw-semibold);
	}
	.scrim {
		display: none;
	}
	.menu {
		display: none;
	}
	.bottom {
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
			border-radius: 0;
			background: var(--bg-scrim);
		}
		main {
			padding: var(--sp-300) var(--sp-200) var(--sp-800);
		}
		.bar {
			gap: var(--sp-100);
			padding: 0 var(--sp-100);
		}
	}
	.scrim.clear {
		display: block;
		position: fixed;
		inset: 0;
		z-index: calc(var(--z-overlay) - 1);
		border: none;
		background: transparent;
	}

	/* A phone: the bottom bar holds Today, Waits and Runs, and Menu opens the whole list as a
	   sheet with the account group in it (ADR-0321 §4). */
	@media (max-width: 599px) {
		.menu,
		.account,
		.trail ol li:not(:last-child) {
			display: none;
		}
		.trail li + li::before {
			content: none;
		}
		.live .said {
			display: none;
		}
		.side {
			inset-block: auto var(--layout-bottombar-height);
			inset-inline: 0;
			width: auto;
			max-height: calc(100vh - var(--layout-appbar-height) - var(--layout-bottombar-height));
			border-start-start-radius: var(--layout-sheet-radius);
			border-start-end-radius: var(--layout-sheet-radius);
			border-inline-end: none;
			transform: translateY(105%);
		}
		.side.open {
			transform: none;
		}
		.scrim {
			inset: 0 0 var(--layout-bottombar-height) 0;
		}
		main {
			padding: var(--sp-250) var(--sp-200) calc(var(--layout-bottombar-height) + var(--sp-500));
		}
		.bottom {
			position: fixed;
			inset-inline: 0;
			inset-block-end: 0;
			z-index: var(--z-sticky);
			display: grid;
			grid-template-columns: repeat(4, 1fr);
			height: var(--layout-bottombar-height);
			padding-block-end: env(safe-area-inset-bottom);
			background: var(--bg-glass);
			backdrop-filter: saturate(1.4) blur(14px);
			border-top: var(--bw-hairline) solid var(--border-subtle);
		}
		.bottom a,
		.bottom button {
			position: relative;
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			gap: var(--sp-025);
			min-height: 0;
			padding: 0;
			border: none;
			border-radius: 0;
			background: transparent;
			text-decoration: none;
			font-size: var(--fs-065);
			font-weight: var(--fw-semibold);
			color: var(--text-secondary);
		}
		.bottom [aria-current='page'] {
			color: var(--text-brand);
		}
		.bottom .waits {
			position: absolute;
			inset-block-start: var(--sp-100);
			inset-inline-start: calc(50% + var(--sp-150));
		}
	}
</style>
