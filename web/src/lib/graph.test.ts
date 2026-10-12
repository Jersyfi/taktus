// The vessels between steps (ADR-0059 §2, amended 2026-10-12): a vessel into a running step
// carries that step's own motion, and nothing else on the graph flows. Without motion, nothing
// flows at all.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import Graph from './Graph.svelte';
import type { RunLevel } from './types';

const LEVEL = fixtures.run_level as unknown as RunLevel;

/** The motion each vessel carries, keyed by the step it leads into. */
function flows(html: string): string[] {
	return [...html.matchAll(/class="core flow-([a-z]+)[^"]*"/g)].map((m) => m[1]!);
}

describe('the vessels of a graph', () => {
	it('carry the motion of the running step they lead into, and only that', () => {
		const html = render(Graph, { props: { steps: LEVEL.steps, motionAllowed: true } }).body;
		const expected = LEVEL.steps.flatMap((s) =>
			(s.depends_on ?? []).filter((d) => LEVEL.steps.some((o) => o.id === d)).map(() => s.drawn.moving.motion)
		);
		expect(flows(html)).toEqual(expected);
		expect(flows(html).some((m) => m !== 'none')).toBe(true);
	});

	it('carry no motion when motion is stopped', () => {
		const html = render(Graph, { props: { steps: LEVEL.steps, motionAllowed: false } }).body;
		expect(flows(html).length).toBeGreaterThan(0);
		expect(flows(html).every((m) => m === 'none')).toBe(true);
	});

	it('carry no motion into a step at rest', () => {
		const resting = LEVEL.steps.map((s) => ({ ...s, drawn: { moving: s.drawn.still, still: s.drawn.still } }));
		const html = render(Graph, { props: { steps: resting, motionAllowed: true } }).body;
		expect(flows(html).length).toBeGreaterThan(0);
		expect(flows(html).every((m) => m === 'none')).toBe(true);
	});
});
