// The introduction in stages (ADR-0137, ADR-0191), drawn from what `GET /stages` answers —
// `fixtures.stages`, written by `make generate` with the route's own functions. The open action
// is offered only where the rule lets the stage open, and no figure names a person.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import IntroductionView from './IntroductionView.svelte';
import { introductionLines, mayOpen, processLine, type Introduction } from './introduction';

const intro = fixtures.stages as unknown as Introduction;

describe('the introduction in stages', () => {
	it('opens with the surface’s summary and shows each stage with its processes and figures', () => {
		const { body } = render(IntroductionView, { props: { intro, onOpen: () => {} } });
		expect(body).toContain(intro.summary);
		expect(body).toContain('Watching');
		expect(body).toContain('error-rate: error-rate@3 at level 3, granted level 3; 21 runs, 0 missed, 0 incidents.');
		expect(body).toContain('Over 3.0 weeks: 42 runs, 0 missed, 1 incidents');
		expect(body).not.toMatch(/idn_/);
	});

	it('offers to open a stage only where its opening lacks nothing', () => {
		const [watch, support, release] = intro.stages;
		expect([watch, support, release].map((s) => mayOpen(s!))).toEqual([false, true, false]);
		const { body } = render(IntroductionView, { props: { intro, onOpen: () => {} } });
		expect(body).toContain('Open stage 2…');
		expect(body).not.toContain('Open stage 3…');
		expect(body).toContain("Its opening lacks: stage 'support' before it is not open.");
	});

	it('says a process that does not run for the tenant in words, and the page as text', () => {
		const release = intro.stages[2]!;
		expect(processLine(release.processes[0]!, false)).toBe('release: not running for the tenant, granted level 3.');
		const lines = introductionLines(intro);
		expect(lines[1]).toContain('It may be opened now.');
		expect(lines[2]).toContain('Its opening lacks');
	});
});
