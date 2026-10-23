// The trace inside a worker's step on the run's page (UC-6.14, ADR-0135): the page asks for
// the lines after the last one it holds, again within two seconds while the step is in flight,
// and no more once it ended; it holds no line twice; a reader the surface refuses, or one who
// may not see the trace, ends it. Each kind of event has a form of its own, a refused call apart
// from a made one, and a share is sent as a role and nothing else.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import { traceLink } from './links';
import { ASK_AGAIN_MS, focused, followTrace, markOf, merged, ROLE, shareAddress, tracePath, traced } from './trace';
import TracePanel from './TracePanel.svelte';
import type { RunLevel, TraceLine, TraceView } from './types';

const LEVEL = fixtures.run_level as unknown as RunLevel;
const BASE = new URL('https://h.test/x/');

function line(position: number, type = 'step.progress', detail: Record<string, unknown> = {}): TraceLine {
	return { position, ts: '2026-10-23T12:00:00Z', type, text: `line ${position}`, detail };
}

function view(lines: TraceLine[], open: boolean): TraceView {
	return {
		run_id: 'run_1',
		step_id: 'w',
		state: open ? 'running' : 'succeeded',
		open,
		lines,
		after: lines.at(-1)?.position ?? 0,
		link: 'app/#/runs/run_1/steps/w'
	};
}

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function withWorker(state: string): RunLevel {
	const step = { ...LEVEL.steps[0]!, id: 'w', method: 'worker', state };
	return { ...LEVEL, steps: [{ ...LEVEL.steps[0]!, id: 'r', method: 'rule', state: 'succeeded' }, step] };
}

describe('the trace of a step', () => {
	it('is asked for again after the last line within two seconds while open, and not after', async () => {
		const answers = [view([line(1), line(2)], true), view([line(2), line(3)], true), view([], false)];
		const asked: string[] = [];
		const slept: number[] = [];
		const seen: number[][] = [];
		const fetcher = (async (url: URL) => {
			asked.push(`${url.pathname}${url.search}`);
			return json(answers.shift());
		}) as typeof fetch;
		await followTrace({
			base: BASE,
			runId: 'run_1',
			stepId: 'w',
			signal: new AbortController().signal,
			fetcher,
			sleep: async (ms) => void slept.push(ms),
			onTrace: (_, lines) => seen.push(lines.map((l) => l.position)),
			onAbsent: () => {
				throw new Error('not absent');
			},
			onRefused: () => {
				throw new Error('not refused');
			}
		});
		expect(asked).toEqual([
			'/x/levels/runs/run_1/steps/w/trace',
			'/x/levels/runs/run_1/steps/w/trace?after=2',
			'/x/levels/runs/run_1/steps/w/trace?after=3'
		]);
		expect(seen).toEqual([[1, 2], [1, 2, 3], [1, 2, 3]]);
		expect(slept).toEqual([ASK_AGAIN_MS, ASK_AGAIN_MS]);
		expect(ASK_AGAIN_MS).toBeLessThanOrEqual(2000);
	});

	it('ends for a reader the surface refuses, and for one who may not see it', async () => {
		for (const [status, expected] of [
			[401, 'refused'],
			[404, 'absent']
		] as const) {
			let ended = '';
			await followTrace({
				base: BASE,
				runId: 'run_1',
				stepId: 'w',
				signal: new AbortController().signal,
				fetcher: (async () => json({ status, title: 'no' }, status)) as typeof fetch,
				onTrace: () => {},
				onAbsent: () => (ended = 'absent'),
				onRefused: () => (ended = 'refused')
			});
			expect(ended).toBe(expected);
		}
	});

	it('holds no line twice', () => {
		expect(merged([line(1), line(2)], [line(2), line(3)]).map((l) => l.position)).toEqual([1, 2, 3]);
		expect(tracePath('run 1', 'w/1', 4)).toBe('levels/runs/run%201/steps/w%2F1/trace?after=4');
	});

	it('draws each kind of event in a form of its own, a refused call apart', () => {
		expect(markOf(line(1, 'tool.called', { refused: true }))).toBe('refused');
		expect(markOf(line(1, 'tool.called'))).toBe('call');
		const forms = ['step.started', 'step.progress', 'decision.made', 'consumption.reported', 'step.boundary', 'artifact.produced', 'assignment.finished'].map((t) => markOf(line(1, t)));
		expect(new Set(forms).size).toBe(forms.length);
	});

	it('is offered for a worker step, and opens at the running one or the one the link names', () => {
		const level = withWorker('running');
		expect(traced(level).map((s) => s.id)).toEqual(['w']);
		expect(focused(level)).toBe('w');
		// A rule step has no trace: the link that names one opens the worker's.
		expect(focused(level, 'r')).toBe('w');
		expect(focused(withWorker('succeeded'), 'w')).toBe('w');
	});

	it('is shared with a role, by a link to the route the surface names', () => {
		expect(ROLE.test('reviewer')).toBe(true);
		for (const person of ['Ada Lovelace', 'ada@example.org', 'idn-ada']) expect(ROLE.test(person)).toBe(false);
		expect(shareAddress(BASE, 'app/#/runs/run_1/steps/w')).toBe('https://h.test/x/app/#/runs/run_1/steps/w');
		expect(`app/${traceLink('run_1', 'w')}`).toBe('app/#/runs/run_1/steps/w');
	});

	it('says to whom it is shown before it is read', () => {
		const { body } = render(TracePanel, {
			props: { level: withWorker('running'), base: BASE, motionAllowed: false, onRefused: () => {} }
		});
		expect(body).toContain('What the worker is doing');
		expect(body).toContain('Reading the trace of w');
	});
});
