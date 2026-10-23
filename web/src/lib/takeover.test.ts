// Taking over a running step from the run's page (UC-4.19, ADR-0128): a running worker step offers
// "take over"; a held one shows the state it reached and until when it is held, and its result
// is read back before it is handed back; a lapsed or refused take-over is said as such.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import RunView from './RunView.svelte';
import TakeoverPanel from './TakeoverPanel.svelte';
import {
	askTakeover,
	described,
	handBack,
	handBackRefused,
	leaseLeft,
	leasePassed,
	offered,
	readResult,
	readState,
	standingOf
} from './takeover';
import type { RunLevel, StepElement, TakeoverState } from './types';

const TAKEN = fixtures.takeover.level as unknown as RunLevel;
const STATE = fixtures.takeover.state as unknown as TakeoverState;
const RUNNING = fixtures.run_level as unknown as RunLevel;
const nothing = () => {};
const handlers = { onTakeOver: nothing, onHandBack: nothing };
const NOW = new Date('2026-10-10T13:00:00Z');

/** The taken-over fixture with no step held, and its build step still running. */
function running(build: Partial<StepElement> = {}): RunLevel {
	return {
		...TAKEN,
		run: { ...TAKEN.run, state: 'running' },
		steps: TAKEN.steps
			.filter((s) => s.id !== 'fix')
			.map((s) => (s.id === 'build' ? { ...s, ...build } : s))
	};
}

describe('a running worker step offers "take over" (UC-4.19 §2)', () => {
	it('offers the running worker steps of a running run, and no step of another method', () => {
		const ids = offered(running()).map((s) => s.id);
		expect(ids).toEqual(['build']);
		expect(offered(RUNNING).every((s) => s.method === 'worker')).toBe(true);
	});

	it('offers nothing while a step of the run is held: only the first ask of a run is taken', () => {
		expect(offered(TAKEN)).toEqual([]);
	});

	it('draws the offer, and reads the ask back before it is sent', () => {
		const html = render(TakeoverPanel, { props: { level: running(), ...handlers } }).body;
		expect(html).toContain('data-offer="build"');
		expect(html).toContain('>Take over<');
		expect(html).not.toContain('data-offer="load"');
	});

	it('sends the ask to the step’s address, and the result to the take-over’s', async () => {
		const seen: { url: string; body: unknown }[] = [];
		const fetcher = (async (url: URL, init?: RequestInit) => {
			seen.push({ url: String(url), body: init?.body ? JSON.parse(String(init.body)) : undefined });
			return new Response(JSON.stringify({ takeover: 'tko_1' }), { status: 202 });
		}) as unknown as typeof fetch;
		const base = new URL('https://taktus.test/p/');
		await askTakeover(base, 'run 1', 'fix', fetcher);
		await readState(base, 'run 1', 'tko_1', fetcher);
		await handBack(base, 'run 1', 'tko_1', { fixed: true }, fetcher);
		expect(seen.map((s) => s.url)).toEqual([
			'https://taktus.test/p/runs/run%201/steps/fix/takeover',
			'https://taktus.test/p/runs/run%201/takeovers/tko_1',
			'https://taktus.test/p/runs/run%201/takeovers/tko_1/hand-back'
		]);
		expect(seen[2]!.body).toEqual({ result: { fixed: true } });
	});
});

describe('a held take-over shows what the step reached and until when (UC-4.19 §2)', () => {
	it('shows the goal, the acceptance criteria, the inputs, the checkpoint and what was produced', () => {
		const html = render(TakeoverPanel, { props: { level: TAKEN, states: { tko_example: STATE }, now: NOW, ...handlers } }).body;
		expect(html).toContain('data-standing="held"');
		expect(html).toContain('Fix the failing test in the parser');
		expect(html).toContain('the suite passes');
		expect(html).toContain('example/repo');
		expect(html).toContain('REPOSITORY_TOKEN');
		expect(html).toContain('ckpt/run_taken/fix/2');
		expect(html).toContain('The patch so far');
		expect(html).toContain('until 2026-10-10 17:00 UTC, 4 h left');
		expect(html).toContain('Read it back');
	});

	it('names no person', () => {
		const html = render(TakeoverPanel, { props: { level: TAKEN, states: { tko_example: STATE }, now: NOW, ...handlers } }).body;
		expect(html).toContain('taken over by a person');
		expect(JSON.stringify(TAKEN)).not.toMatch(/actor|by_person|identity/);
	});

	it('measures how much of the lease has passed, and says when it has run out', () => {
		expect(leasePassed('2026-10-10T09:00:00Z', '2026-10-10T17:00:00Z', NOW)).toBeCloseTo(0.5);
		expect(leaseLeft('2026-10-10T17:00:00Z', new Date('2026-10-10T18:00:00Z'))).toContain('the time has run out');
	});

	it('draws the step as taken over in the run’s graph', () => {
		const html = render(RunView, { props: { level: TAKEN, motionAllowed: false } }).body;
		expect(html).toContain('taken over: tko_example');
	});
});

describe('the result is read back before it is handed back (ADR-0008)', () => {
	it('reads JSON as JSON, and anything else as the text written', () => {
		expect(readResult('{"fixed": true, "tests": 12}')).toEqual({ form: 'json', value: { fixed: true, tests: 12 } });
		expect(readResult('fixed it')).toEqual({ form: 'text', value: 'fixed it' });
		expect(readResult('   ')).toBeNull();
	});

	it('says how the result was read, in words', () => {
		expect(described({ form: 'json', value: { fixed: true, tests: 12 } })).toBe('as a JSON object with the fields fixed, tests');
		expect(described({ form: 'json', value: [1, 2] })).toBe('as a JSON list of 2 values');
		expect(described({ form: 'text', value: 'fixed it' })).toBe('as text, exactly as you wrote it (8 characters)');
	});

	it('says why a hand-back was refused: a lapse is not an unknown take-over', () => {
		expect(handBackRefused(409, '')).toContain('time ran out');
		expect(handBackRefused(404, '')).toContain('No step is held');
	});
});

describe('a lapsed or refused take-over is shown as such (UC-4.19 §2)', () => {
	it('shows a lapsed take-over from the run level', () => {
		const html = render(TakeoverPanel, { props: { level: TAKEN, now: NOW, ...handlers } }).body;
		expect(html).toContain('data-takeover="tko_lapsed"');
		expect(html).toMatch(/data-standing="lapsed"/);
		expect(html).toContain('went back to its worker at its checkpoint');
	});

	it('keeps an ask waiting while its step runs, and calls it refused once the step ended otherwise', () => {
		const asked = { takeover: 'tko_new', step: 'build' };
		expect(standingOf(running(), asked)).toBe('asked');
		expect(standingOf(running({ state: 'succeeded' }), asked)).toBe('refused');
		const html = render(TakeoverPanel, {
			props: { level: running({ state: 'succeeded' }), asked, ...handlers }
		}).body;
		expect(html).toContain('data-standing="refused"');
		expect(html).toContain('was refused');
	});

	it('follows a served ask by what the run level says of it', () => {
		expect(standingOf(TAKEN, { takeover: 'tko_example', step: 'fix' })).toBe('held');
		expect(standingOf(TAKEN, { takeover: 'tko_lapsed', step: 'lint' })).toBe('lapsed');
	});
});
