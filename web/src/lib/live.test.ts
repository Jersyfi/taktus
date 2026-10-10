import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import { surface } from './api';
import { applyToRuns, followLevel, Rereader, type Runs } from './live';
import type { RunLevel } from './types';

const LEVEL = fixtures.run_level as unknown as RunLevel;

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': status < 400 ? 'application/json' : 'application/problem+json' }
	});
}

function stream(text: string): Response {
	return new Response(new TextEncoder().encode(text), { status: 200 });
}

describe('the surface', () => {
	it('is the directory above the app, whatever the prefix', () => {
		expect(String(surface('https://h.test/a/b/app/#/runs/r1'))).toBe('https://h.test/a/b/');
		expect(String(surface('https://h.test/app/'))).toBe('https://h.test/');
	});
});

describe('the runs of the tenant stream', () => {
	it('start from the snapshot and move with each change', () => {
		let runs: Runs = new Map();
		runs = applyToRuns(runs, {
			kind: 'snapshot',
			snapshot: {
				position: 'h1',
				scope: { kind: 'tenant' },
				runs: [{ id: 'r1', process_version: 'p@1', state: 'running', steps: [] }]
			}
		});
		runs = applyToRuns(runs, {
			kind: 'change',
			change: {
				position: 'h2',
				run: 'r1',
				step: 'a',
				kind: 'step.finished',
				outcome: 'succeeded',
				recorded_at: 't',
				state: { step: 'succeeded', run: 'finished' }
			}
		});
		expect(runs.get('r1')).toEqual({
			id: 'r1',
			process_version: 'p@1',
			state: 'finished',
			steps: [{ id: 'a', state: 'succeeded', method: '' }]
		});
	});
});

describe('reading again', () => {
	it('costs one more read for a burst of requests, not one per request', async () => {
		let reads = 0;
		let release: () => void = () => {};
		const rereader = new Rereader(async () => {
			reads += 1;
			if (reads === 1) await new Promise<void>((r) => (release = r));
		});
		const first = rereader.request();
		void rereader.request();
		void rereader.request();
		release();
		await first;
		expect(reads).toBe(2);
	});
});

describe('a level followed live', () => {
	it('is read on the snapshot and read again on a change, without a reload', async () => {
		const later: RunLevel = { ...LEVEL, run: { ...LEVEL.run, state: 'finished' } };
		const levels = [LEVEL, later];
		const seen: RunLevel[] = [];
		const requested: string[] = [];
		const fetcher = (async (url: URL) => {
			requested.push(`${url.pathname}${url.search}`);
			if (url.pathname.endsWith('/changes')) {
				if (requested.filter((r) => r.startsWith('/x/changes')).length > 1) {
					return new Response(null, { status: 401 });
				}
				return stream(
					'event: snapshot\nid: h1\ndata: {"position":"h1","scope":{"kind":"run","id":"run_example"},"runs":[]}\n\n' +
						'event: change\nid: h2\ndata: {"position":"h2","run":"run_example","kind":"run.finished","recorded_at":"t","state":{"run":"finished"}}\n\n'
				);
			}
			return json(levels.shift() ?? later);
		}) as unknown as typeof fetch;
		let refused = false;
		await followLevel<RunLevel>({
			base: new URL('https://h.test/x/'),
			path: 'levels/runs/run_example',
			scope: { run: 'run_example' },
			key: 'tk',
			signal: new AbortController().signal,
			onLevel: (l) => seen.push(l),
			onAbsent: () => {},
			onRefused: () => (refused = true),
			fetcher,
			// The stream stays away a moment before it reconnects, and is then refused.
			sleep: () => new Promise((r) => setTimeout(r, 20))
		});
		expect(requested[0]).toBe('/x/changes?run=run_example');
		expect(seen.map((l) => l.run.state)).toContain('finished');
		expect(seen.at(-1)!.run.state).toBe('finished');
		expect(refused).toBe(true);
	});

	it('tells a level the reader may not see as absent', async () => {
		let absent = false;
		const fetcher = (async (url: URL) =>
			url.pathname.endsWith('/changes')
				? stream('event: snapshot\nid: h1\ndata: {"position":"h1","scope":{"kind":"run","id":"r"}}\n\n')
				: json({ status: 404, title: 'Not found', detail: "no run 'r' you may see" }, 404)) as unknown as typeof fetch;
		const controller = new AbortController();
		await followLevel<RunLevel>({
			base: new URL('https://h.test/'),
			path: 'levels/runs/r',
			scope: { run: 'r' },
			key: 'tk',
			signal: controller.signal,
			onLevel: () => {},
			onAbsent: () => {
				absent = true;
				controller.abort();
			},
			onRefused: () => {},
			fetcher,
			sleep: async () => {
				await new Promise((r) => setTimeout(r, 1));
			}
		});
		expect(absent).toBe(true);
	});
});
