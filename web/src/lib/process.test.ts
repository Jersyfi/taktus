// The process level draws what it is handed and nothing else (ADR-0059 §3, ADR-0064): every
// step's glyph and every run's, with motion and without, the autonomy statement, links down to
// the runs and to the other versions, and the whole again as text.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import { processLink, runLink } from './links';
import ProcessView from './ProcessView.svelte';
import type { Glyph as GlyphTokens, ProcessLevel } from './types';

const LEVEL = fixtures.process_level as unknown as ProcessLevel;

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

function elements(level: ProcessLevel) {
	return [...level.steps, ...(level.runs ?? [])];
}

describe('the process level', () => {
	it('draws every step and every run as handed over, with motion', () => {
		const html = render(ProcessView, { props: { level: LEVEL, motionAllowed: true } }).body;
		expect(drawnIn(html)).toEqual(elements(LEVEL).map((e) => handedOver(e.drawn.moving)));
		const moving = LEVEL.steps.filter((s) => s.running_in?.length).map((s) => s.id);
		expect(moving).toEqual(['score', 'draft', 'review']);
		expect(drawnIn(html).filter((g) => g['data-motion'] !== 'none').length).toBe(moving.length);
	});

	it('without motion draws every still glyph, and nothing moves', () => {
		const html = render(ProcessView, { props: { level: LEVEL, motionAllowed: false } }).body;
		const drawn = drawnIn(html);
		expect(drawn).toEqual(elements(LEVEL).map((e) => handedOver(e.drawn.still)));
		expect(drawn.every((g) => g['data-motion'] === 'none')).toBe(true);
	});

	it('draws no motion for a version no run is running', () => {
		const idle: ProcessLevel = {
			...LEVEL,
			steps: LEVEL.steps.filter((s) => !s.running_in?.length),
			runs: []
		};
		const html = render(ProcessView, { props: { level: idle, motionAllowed: true } }).body;
		expect(drawnIn(html).every((g) => g['data-motion'] === 'none')).toBe(true);
	});

	it('shows the autonomy statement with the process', () => {
		const html = unescape(render(ProcessView, { props: { level: LEVEL, motionAllowed: true } }).body);
		expect(html).toContain(`data-autonomy-level="${LEVEL.process.autonomy.level}"`);
		expect(html).toContain(LEVEL.process.autonomy_text);
		expect(LEVEL.process.autonomy_text).toContain(LEVEL.process.autonomy.reason);
	});

	it('leads down to its runs, and writes every element out as text', () => {
		const html = unescape(render(ProcessView, { props: { level: LEVEL, motionAllowed: true } }).body);
		for (const run of LEVEL.runs ?? []) expect(html).toContain(`href="${runLink(run.id)}"`);
		expect(html).toContain(LEVEL.process.text);
		for (const element of elements(LEVEL)) expect(html).toContain(element.text);
	});
});

describe('links', () => {
	it('name a run, a process version and a bare process', () => {
		expect(runLink('run 1')).toBe('#/runs/run%201');
		expect(processLink('invoices@2')).toBe('#/processes/invoices/2');
		expect(processLink('invoices')).toBe('#/processes/invoices');
		expect(processLink('a@b@3')).toBe('#/processes/a%40b/3');
	});
});
