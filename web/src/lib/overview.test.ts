// The overview draws what it is handed and nothing else (ADR-0059 §3, ADR-0067): the steps
// running right now, with motion and without, how many runs of each process work and wait, the
// links down to each process and run, and the same again as text.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import { processLink, runLink } from './links';
import OverviewView from './OverviewView.svelte';
import type { Glyph as GlyphTokens, OverviewLevel } from './types';

const LEVEL = fixtures.overview as unknown as OverviewLevel;

const TOKENS = [
	['subject', 'data-subject'],
	['outline', 'data-outline'],
	['edge', 'data-edge'],
	['exactness_mark', 'data-exactness-mark'],
	['fill', 'data-fill'],
	['state_mark', 'data-state-mark'],
	['motion', 'data-motion'],
	['still_mark', 'data-still-mark']
] as const;

function unescape(text: string): string {
	return text
		.replaceAll('&amp;', '&')
		.replaceAll('&lt;', '<')
		.replaceAll('&gt;', '>')
		.replaceAll('&quot;', '"')
		.replaceAll('&#39;', "'");
}

function drawnIn(html: string): Record<string, string>[] {
	const found: Record<string, string>[] = [];
	for (const match of html.matchAll(/<svg class="glyph[^"]*"([^>]*)>\s*<title[^>]*>([^<]*)<\/title>/g)) {
		const attributes: Record<string, string> = {};
		for (const a of match[1]!.matchAll(/(data-[a-z-]+)="([^"]*)"/g)) attributes[a[1]!] = a[2]!;
		attributes['text'] = unescape(match[2]!);
		found.push(attributes);
	}
	return found;
}

function handedOver(glyph: GlyphTokens): Record<string, string> {
	const tokens: Record<string, string> = { text: glyph.text };
	for (const [field, attribute] of TOKENS) {
		const value = glyph[field];
		if (value !== undefined) tokens[attribute] = value;
	}
	return tokens;
}

const processes = LEVEL.areas.flatMap((a) => a.processes);
const running = processes.flatMap((p) => p.running ?? []);

describe('the overview', () => {
	it('draws the steps running right now as handed over, with motion and without', () => {
		expect(running.length).toBeGreaterThan(0);
		const moving = render(OverviewView, { props: { level: LEVEL, motionAllowed: true } }).body;
		expect(drawnIn(moving)).toEqual(running.map((s) => handedOver(s.drawn.moving)));
		const still = render(OverviewView, { props: { level: LEVEL, motionAllowed: false } }).body;
		expect(drawnIn(still)).toEqual(running.map((s) => handedOver(s.drawn.still)));
		expect(drawnIn(still).every((g) => g['data-motion'] === 'none')).toBe(true);
	});

	it('draws nothing that moves where nothing runs', () => {
		const idle: OverviewLevel = {
			areas: LEVEL.areas.map((a) => ({
				...a,
				working: 0,
				processes: a.processes.map((p) => ({ ...p, working: 0, running: [] }))
			}))
		};
		const html = render(OverviewView, { props: { level: idle, motionAllowed: true } }).body;
		expect(drawnIn(html)).toEqual([]);
	});

	it('shows how many runs of each process work and wait, as handed over', () => {
		const html = render(OverviewView, { props: { level: LEVEL, motionAllowed: true } }).body;
		for (const process of processes) {
			expect(html).toMatch(
				new RegExp(`data-figures="process:${process.id}"[^>]*>\\s*${process.working} working · ${process.waiting} waiting`)
			);
		}
		const [area] = LEVEL.areas;
		expect(html).toMatch(new RegExp(`data-figures="area:${area!.id}"[^>]*>\\s*${area!.working} working · ${area!.waiting} waiting`));
	});

	it('leads down to each process and each running step, and writes everything out as text', () => {
		const html = unescape(render(OverviewView, { props: { level: LEVEL, motionAllowed: true } }).body);
		for (const p of processes) {
			const ref = p.active_version ? `${p.id}@${p.active_version}` : p.id;
			expect(html).toContain(`href="${processLink(ref)}"`);
			expect(html).toContain(p.text);
		}
		for (const s of running) {
			expect(html).toContain(`href="${runLink(s.run)}"`);
			expect(html).toContain(s.text);
		}
		for (const a of LEVEL.areas) expect(html).toContain(a.text);
	});
});
