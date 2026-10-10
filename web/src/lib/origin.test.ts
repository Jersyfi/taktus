// The origin of a result draws what it is handed and nothing else (ADR-0059 §3, ADR-0068): the
// result, each step on the path and each source, none of them moving; the decision request a
// step raised at the run level; and every token of the vocabulary's new forms has a drawing.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import { originLink, runLink } from './links';
import OriginView from './OriginView.svelte';
import RunView from './RunView.svelte';
import { known, OUTLINES, STATE_MARKS } from './shapes';
import type { Glyph as GlyphTokens, OriginLevel, RunLevel } from './types';

const LEVEL = fixtures.origin as unknown as OriginLevel;
const RUN = fixtures.run_level as unknown as RunLevel;

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

const sources = LEVEL.sources ?? [];
const inOrder = [...sources, ...[...LEVEL.steps].reverse(), LEVEL.result];

describe('the origin of a result', () => {
	it('draws the result, every step and every source as handed over, and nothing moves', () => {
		for (const motionAllowed of [true, false]) {
			const html = render(OriginView, { props: { level: LEVEL, motionAllowed } }).body;
			const key = motionAllowed ? 'moving' : 'still';
			expect(drawnIn(html)).toEqual(inOrder.map((e) => handedOver(e.drawn[key])));
			expect(drawnIn(html).every((g) => g['data-motion'] === 'none')).toBe(true);
		}
	});

	it('leads to the run, and writes every element out as text', () => {
		const html = unescape(render(OriginView, { props: { level: LEVEL, motionAllowed: true } }).body);
		expect(html).toContain(`href="${runLink(LEVEL.result.run)}"`);
		for (const element of inOrder) expect(html).toContain(element.text);
	});

	it('has a drawing for the outlines and marks of a result, a source and a decision request', () => {
		const vocabulary = fixtures.vocabulary;
		for (const outline of [vocabulary.result_outline, vocabulary.source_outline, vocabulary.decision_outline]) {
			expect(known(outline, OUTLINES), outline).toBe(true);
		}
		for (const s of vocabulary.states) expect(known(s.mark, STATE_MARKS), s.mark).toBe(true);
	});
});

describe('the run level', () => {
	it('draws the decision request a step raised, and leads to the origin of each result', () => {
		const html = unescape(render(RunView, { props: { level: RUN, motionAllowed: true } }).body);
		const decisions = RUN.steps.flatMap((s) => s.decisions ?? []);
		expect(decisions.length).toBeGreaterThan(0);
		for (const d of decisions) expect(drawnIn(html)).toContainEqual(handedOver(d.drawn.moving));
		const produced = RUN.steps.filter((s) => s.state === 'succeeded' && s.exactness);
		for (const s of produced) expect(html).toContain(`href="${originLink(RUN.run.id, s.id)}"`);
	});
});
