<!--
	The frame of every level: the mark, the depth the reader stands at — overview, process, run,
	origin — and the control that stops all motion. Paper and ink; a family's hue is added only on
	the cells (M1.20, DEC-0185). Signing out ends the reader's session on the instance (ADR-0119).
-->
<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import { page } from '$app/state';
	import { surface } from '../lib/api';
	import { motion } from '../lib/motion.svelte';
	import { forgetOldKey, signOut } from '../lib/session';

	let { children }: { children: Snippet } = $props();

	onMount(() => {
		forgetOldKey();
		return motion.listen();
	});

	async function leave() {
		await signOut(surface(location.href));
		location.reload();
	}

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
	const calm = $derived(motion.stoppedByReader || motion.reducedBySystem);
</script>

<div class="page">
	<header class="bar">
		<a class="home" href="#/"><span class="mark" aria-hidden="true"></span>taktus</a>
		<nav class="depth" aria-label="Depth">
			{#each DEPTHS as name, i (name)}
				{#if i > 0}<span class="rail" aria-hidden="true"></span>{/if}
				{#if i === 0 && depth !== 0}
					<a class="stop done" href="#/">{name}</a>
				{:else}
					<span class="stop" class:done={i < depth} class:here={i === depth} aria-current={i === depth ? 'page' : undefined}
						>{name}</span>
				{/if}
			{/each}
		</nav>
		<a class="requests" href="#/register" aria-current={page.route.id === '/register' ? 'page' : undefined}>What acts</a>
		<a class="requests" href="#/gallery" aria-current={page.route.id === '/gallery' ? 'page' : undefined}>Gallery</a>
		<a class="requests" href="#/me" aria-current={page.route.id === '/me' ? 'page' : undefined}>Yours</a>
		<a class="requests" href="#/trials" aria-current={page.route.id?.startsWith('/trials') ? 'page' : undefined}>Trials</a>
		<a class="requests" href="#/requests" aria-current={page.route.id?.startsWith('/requests') ? 'page' : undefined}>Requests</a>
		<button
			class="calm"
			type="button"
			aria-pressed={calm}
			disabled={motion.reducedBySystem}
			onclick={() => (motion.stoppedByReader = !motion.stoppedByReader)}
		>
			Stop motion{#if motion.reducedBySystem}&#32;(the system asks for it){/if}
		</button>
		<button class="calm" type="button" onclick={leave}>Sign out</button>
	</header>
	<main>
		{@render children()}
	</main>
</div>

<style>
	/* Paper and ink. A family's hue is added on top of its form (M1.20, DEC-0185); every
	   distinction is already carried by membrane, nucleus and motion. */
	:global(:root) {
		--paper: oklch(0.972 0.007 85);
		--paper-2: oklch(0.948 0.009 85);
		--ink: oklch(0.23 0.012 260);
		--ink-2: oklch(0.46 0.012 260);
		--ink-3: oklch(0.62 0.01 260);
		--line: oklch(0.86 0.01 85);
		--reproducible: oklch(0.5 0.12 240);
		--variable: oklch(0.6 0.16 50);
		--person: oklch(0.52 0.12 150);
		--waiting: oklch(0.55 0.01 260);
		--alert: oklch(0.55 0.17 28);
		--focus: oklch(0.55 0.17 255);
		--serif: 'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, serif;
		--sans: system-ui, -apple-system, 'Segoe UI', sans-serif;
		--mono: ui-monospace, 'SF Mono', Menlo, monospace;
		--text: var(--ink);
		--muted: var(--ink-2);
		--surface: var(--paper);
		color-scheme: light dark;
	}
	@media (prefers-color-scheme: dark) {
		:global(:root) {
			--paper: oklch(0.165 0.008 260);
			--paper-2: oklch(0.198 0.009 260);
			--ink: oklch(0.94 0.008 85);
			--ink-2: oklch(0.74 0.01 85);
			--ink-3: oklch(0.58 0.01 85);
			--line: oklch(0.29 0.01 260);
			--reproducible: oklch(0.76 0.11 235);
			--variable: oklch(0.8 0.13 65);
			--person: oklch(0.78 0.12 150);
			--waiting: oklch(0.68 0.01 260);
			--alert: oklch(0.72 0.15 30);
			--focus: oklch(0.75 0.14 255);
		}
	}
	:global(body) {
		margin: 0;
		background: var(--paper);
		color: var(--ink);
		font: 400 15px/1.5 var(--sans);
		font-variant-numeric: tabular-nums;
	}
	:global(a) {
		color: inherit;
	}
	:global(:focus-visible) {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
		border-radius: 6px;
	}
	/* Each level opens with a sentence: what is happening, before the picture. */
	:global(h1) {
		font-family: var(--serif);
		font-weight: 400;
		font-size: clamp(1.8rem, 4vw, 2.9rem);
		line-height: 1.1;
		letter-spacing: -0.01em;
		margin: 0 0 0.5rem;
		text-wrap: balance;
	}
	:global(h2) {
		font-size: 0.8rem;
		font-weight: 500;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-2);
	}
	/* Every level's text equivalent: the same states and figures, set as a quiet list. */
	:global(section.text) {
		margin-top: 2.5rem;
	}
	:global(section.text ol) {
		font-family: var(--mono);
		font-size: 0.82rem;
		line-height: 1.75;
		background: var(--paper-2);
		border-radius: 14px;
		padding: 1.1rem 1.25rem 1.1rem 2.75rem;
		overflow-x: auto;
	}
	.page {
		max-width: 80rem;
		margin: 0 auto;
		padding: 0 1.75rem 4rem;
	}
	.bar {
		position: sticky;
		top: 0;
		z-index: 2;
		display: flex;
		align-items: center;
		gap: 1.25rem;
		flex-wrap: wrap;
		padding: 0.75rem 0;
		margin-bottom: 1.75rem;
		background: color-mix(in oklch, var(--paper) 90%, transparent);
		backdrop-filter: blur(10px);
		border-bottom: 1px solid var(--line);
	}
	.home {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		font-weight: 600;
		font-size: 1.1rem;
		letter-spacing: -0.02em;
		text-decoration: none;
	}
	/* The mark: a small reproducible cell, still. */
	.mark {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		border: 1.5px solid var(--reproducible);
		box-shadow:
			inset 0 0 0 2.5px var(--paper),
			inset 0 0 0 6px var(--reproducible);
	}
	.depth {
		display: flex;
		align-items: center;
		flex: 1;
		min-width: 0;
		overflow: hidden;
		font-size: 0.82rem;
		color: var(--ink-3);
	}
	.stop {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		white-space: nowrap;
		text-decoration: none;
	}
	.stop::before {
		content: '';
		width: 7px;
		height: 7px;
		border-radius: 50%;
		border: 1.5px solid currentColor;
		flex: none;
	}
	.stop.done {
		color: var(--ink-2);
	}
	.stop.done::before {
		background: currentColor;
	}
	.stop.here {
		color: var(--ink);
		font-weight: 500;
	}
	.stop.here::before {
		background: var(--ink);
		border-color: var(--ink);
	}
	.rail {
		width: 1.75rem;
		height: 1px;
		margin: 0 0.5rem;
		background: var(--line);
		flex: none;
	}
	.requests {
		font-size: 0.85rem;
		text-decoration: none;
		border: 1px solid var(--line);
		border-radius: 999px;
		padding: 0.35rem 0.8rem;
	}
	.requests[aria-current='page'] {
		background: var(--paper-2);
	}
	.calm {
		border: 1px solid var(--line);
		background: var(--paper);
		border-radius: 999px;
		padding: 0.35rem 0.8rem;
		font: inherit;
		font-size: 0.85rem;
		cursor: pointer;
		color: var(--ink);
	}
	.calm[aria-pressed='true'] {
		background: var(--ink);
		color: var(--paper);
		border-color: var(--ink);
	}
	.calm:disabled {
		cursor: default;
	}
	@media (max-width: 760px) {
		.page {
			padding: 0 1rem 3rem;
		}
		.depth {
			order: 3;
			flex-basis: 100%;
		}
		.rail {
			width: 0.9rem;
			margin: 0 0.3rem;
		}
		.stop:not(.here):not(.done) {
			font-size: 0;
			gap: 0;
		}
	}
</style>
