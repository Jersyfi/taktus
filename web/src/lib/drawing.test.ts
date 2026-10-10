// The web app draws what it is handed and nothing else (ADR-0059 §3, ADR-0063).
//
// The glyphs come from `reporting`: `make generate` draws a run level from example facts that use
// every method kind, every exactness class and every motion, and writes it beside the vocabulary
// (`generated/fixtures.json`; a Python test fails a stale copy). These tests render the web app's
// drawing and read back every token it drew: a token other than the one handed over fails.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import Glyph from './Glyph.svelte';
import RunView from './RunView.svelte';
import { EDGES, EXACTNESS_MARKS, FILLS, known, MOTIONS, OUTLINES, STATE_MARKS, STILL_MARKS } from './shapes';
import type { Glyph as GlyphTokens, RunLevel } from './types';

const LEVEL = fixtures.run_level as unknown as RunLevel;
const VOCABULARY = fixtures.vocabulary;

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

/** Every glyph drawn in some HTML, as the tokens its data attributes carry, and its text. */
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

function unescape(text: string): string {
	return text.replaceAll('&amp;', '&').replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"').replaceAll('&#39;', "'");
}

function handedOver(glyph: GlyphTokens): Record<string, string> {
	const tokens: Record<string, string> = { text: glyph.text };
	for (const [field, attribute] of TOKENS) {
		const value = glyph[field];
		if (value !== undefined) tokens[attribute] = value;
	}
	return tokens;
}

function elements(level: RunLevel) {
	return [level.run, ...level.steps];
}

describe('a glyph', () => {
	it('draws every token it was handed, and no other, with motion and without', () => {
		for (const element of elements(LEVEL)) {
			for (const glyph of [element.drawn.moving, element.drawn.still]) {
				const html = render(Glyph, { props: { glyph } }).body;
				expect(drawnIn(html)).toEqual([handedOver(glyph)]);
			}
		}
	});

	it('fails a drawing that carries another token than the one handed over', () => {
		const glyph = LEVEL.steps[0]!.drawn.moving;
		const html = render(Glyph, { props: { glyph } }).body.replace(
			`data-outline="${glyph.outline}"`,
			'data-outline="star"'
		);
		expect(drawnIn(html)).not.toEqual([handedOver(glyph)]);
	});

	it('has a drawing for every token of the vocabulary', () => {
		for (const m of VOCABULARY.methods) expect(known(m.outline, OUTLINES), m.outline).toBe(true);
		expect(known(VOCABULARY.run_outline, OUTLINES)).toBe(true);
		for (const f of VOCABULARY.families) {
			expect(known(f.edge, EDGES), f.edge).toBe(true);
			expect(known(f.motion, MOTIONS), f.motion).toBe(true);
		}
		for (const m of VOCABULARY.motions) expect(known(m.still, STILL_MARKS), m.still).toBe(true);
		for (const e of VOCABULARY.exactness) expect(known(e.mark, EXACTNESS_MARKS), e.mark).toBe(true);
		for (const s of VOCABULARY.states) {
			expect(known(s.fill, FILLS), s.fill).toBe(true);
			expect(known(s.mark, STATE_MARKS), s.mark).toBe(true);
		}
	});
});

describe('the run level', () => {
	it('draws every element as handed over, with motion', () => {
		const html = render(RunView, { props: { level: LEVEL, motionAllowed: true } }).body;
		expect(drawnIn(html)).toEqual(elements(LEVEL).map((e) => handedOver(e.drawn.moving)));
		expect(drawnIn(html).filter((g) => g['data-motion'] !== 'none').length).toBe(3);
	});

	it('without motion draws every still glyph: nothing moves, and nothing else changes', () => {
		const html = render(RunView, { props: { level: LEVEL, motionAllowed: false } }).body;
		const drawn = drawnIn(html);
		expect(drawn).toEqual(elements(LEVEL).map((e) => handedOver(e.drawn.still)));
		expect(drawn.every((g) => g['data-motion'] === 'none')).toBe(true);
		expect(html).not.toMatch(/class="glyph motion-(pulse|shimmer|swell)"/);
	});

	it('draws no motion for a run where nothing runs', () => {
		const idle: RunLevel = {
			...LEVEL,
			steps: LEVEL.steps.filter((s) => s.drawn.moving.motion === 'none')
		};
		const html = render(RunView, { props: { level: idle, motionAllowed: true } }).body;
		expect(drawnIn(html).every((g) => g['data-motion'] === 'none')).toBe(true);
	});

	it('writes every element out as text, with the same states and figures', () => {
		const html = unescape(render(RunView, { props: { level: LEVEL, motionAllowed: true } }).body);
		for (const element of elements(LEVEL)) expect(html).toContain(element.text);
		const figures = (LEVEL.run.consumed ?? []).map((f) => `${f.name} ${f.value}`).join(', ');
		expect(html).toMatch(new RegExp(`data-figures="run"[^>]*>${figures.replaceAll('.', '\\.')}<`));
		const waiting = LEVEL.steps.find((s) => s.wait)!;
		expect(html).toContain(`waits: ${waiting.wait!.account}`);
	});
});
