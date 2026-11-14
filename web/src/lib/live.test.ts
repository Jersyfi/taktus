// A level read at once and again when the frame's one stream says something concerns it
// (ADR-0063, ADR-0323): the stream itself, how a level watches it, and what a failure shows.

import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import { read, surface } from './api';
import { ofProcess, ofRun, Rereader, watchLevel, type Hub } from './live';
import { TenantStream } from './pulse';
import type { StreamEvent } from './stream';
import type { Change, Problem, RunLevel } from './types';

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

/** A stream the test drives by hand. */
class FakeHub implements Hub {
	private listeners = new Set<(event: StreamEvent) => void>();
	subscribe(listener: (event: StreamEvent) => void): () => void {
		this.listeners.add(listener);
		return () => this.listeners.delete(listener);
	}
	emit(event: StreamEvent): void {
		for (const l of this.listeners) l(event);
	}
	get listening(): number {
		return this.listeners.size;
	}
}

function change(run: string, extra: Partial<Change> = {}): StreamEvent {
	return { kind: 'change', change: { position: `p-${run}-${Math.random()}`, run, kind: 'step.finished', recorded_at: 't', state: { step: 'succeeded' }, ...extra } };
}

const tick = () => new Promise((r) => setTimeout(r, 5));

describe('the surface', () => {
	it('is the directory above the app, whatever the prefix', () => {
		expect(String(surface('https://h.test/a/b/app/#/runs/r1'))).toBe('https://h.test/a/b/');
		expect(String(surface('https://h.test/app/'))).toBe('https://h.test/');
	});

	it('answers a request that never reached it as a failure, never by throwing (ADR-0322 §5)', async () => {
		const gone = (async () => {
			throw new TypeError('Failed to fetch');
		}) as unknown as typeof fetch;
		const answer = await read(new URL('https://h.test/'), 'levels/overview', gone);
		expect(answer.ok).toBe(false);
		if (!answer.ok) expect(answer.problem.status).toBe(0);
		const garbled = (async () => new Response('<html>', { status: 200 })) as unknown as typeof fetch;
		const second = await read(new URL('https://h.test/'), 'levels/overview', garbled);
		expect(second.ok).toBe(false);
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

describe('a level watched on the frame’s stream', () => {
	it('is read at once, without waiting for the stream (ADR-0323 §2)', async () => {
		const seen: RunLevel[] = [];
		const hub = new FakeHub();
		watchLevel<RunLevel>({
			base: new URL('https://h.test/x/'),
			path: 'levels/runs/run_example',
			concerns: ofRun('run_example'),
			hub,
			signal: new AbortController().signal,
			onLevel: (l) => seen.push(l),
			onAbsent: () => {},
			onRefused: () => {},
			onFailed: () => {},
			fetcher: (async () => json(LEVEL)) as unknown as typeof fetch
		});
		await tick();
		expect(seen.length).toBe(1);
	});

	it('is read again on a change that concerns it and on a reconnect, and not on another run’s change', async () => {
		let reads = 0;
		const hub = new FakeHub();
		const controller = new AbortController();
		watchLevel<RunLevel>({
			base: new URL('https://h.test/x/'),
			path: 'levels/runs/run_example',
			concerns: ofRun('run_example'),
			hub,
			signal: controller.signal,
			onLevel: () => {},
			onAbsent: () => {},
			onRefused: () => {},
			onFailed: () => {},
			fetcher: (async () => {
				reads += 1;
				return json(LEVEL);
			}) as unknown as typeof fetch
		});
		await tick();
		hub.emit(change('another_run'));
		await tick();
		expect(reads).toBe(1);
		hub.emit(change('run_example'));
		await tick();
		expect(reads).toBe(2);
		hub.emit({ kind: 'snapshot', snapshot: { position: 'p9', scope: { kind: 'tenant' } } });
		await tick();
		expect(reads).toBe(3);
		controller.abort();
		expect(hub.listening).toBe(0);
	});

	it('says a 5xx as a failure, never as a read that goes on (ADR-0322 §5)', async () => {
		let problem: Problem | null = null;
		let level: RunLevel | null = null;
		watchLevel<RunLevel>({
			base: new URL('https://h.test/'),
			path: 'levels/runs/r',
			concerns: ofRun('r'),
			hub: new FakeHub(),
			signal: new AbortController().signal,
			onLevel: (l) => (level = l),
			onAbsent: () => {},
			onRefused: () => {},
			onFailed: (p) => (problem = p),
			fetcher: (async () => json({ status: 503, title: 'Service Unavailable', detail: 'the database is away' }, 503)) as unknown as typeof fetch
		});
		await tick();
		expect(level).toBeNull();
		expect((problem as Problem | null)?.status).toBe(503);
	});

	it('tells a level the reader may not see as absent, and a reader without a sign-in as refused', async () => {
		let absent = false;
		let refused = false;
		const base = new URL('https://h.test/');
		const watch = (status: number) =>
			watchLevel<RunLevel>({
				base,
				path: 'levels/runs/r',
				concerns: ofRun('r'),
				hub: new FakeHub(),
				signal: new AbortController().signal,
				onLevel: () => {},
				onAbsent: () => (absent = true),
				onRefused: () => (refused = true),
				onFailed: () => {},
				fetcher: (async () => json({ status, title: '', detail: '' }, status)) as unknown as typeof fetch
			});
		watch(404);
		watch(401);
		await tick();
		expect(absent).toBe(true);
		expect(refused).toBe(true);
	});

	it('takes a change without a process as one that may concern any process', () => {
		const concerns = ofProcess('invoices');
		const base: Change = { position: 'p', run: 'r', kind: 'run.started', recorded_at: 't', state: { run: 'running' } };
		expect(concerns(base)).toBe(true);
		expect(concerns({ ...base, process: { id: 'invoices', version: '2' } })).toBe(true);
		expect(concerns({ ...base, process: { id: 'payroll', version: '1' } })).toBe(false);
	});
});

describe('the frame’s stream of the tenant', () => {
	it('asks for the snapshot’s position only, and counts and keeps each change, not its snapshot', async () => {
		const requested: string[] = [];
		let opened = 0;
		const fetcher = (async (url: URL) => {
			requested.push(`${url.pathname}${url.search}`);
			opened += 1;
			if (opened > 1) return new Response(null, { status: 401 });
			return stream(
				'event: snapshot\nid: h1\ndata: {"position":"h1","scope":{"kind":"tenant"}}\n\n' +
					'event: change\nid: h2\ndata: {"position":"h2","run":"r1","kind":"step.admitted","recorded_at":"t","state":{"run":"running"}}\n\n' +
					'event: change\nid: h3\ndata: {"position":"h3","run":"r1","kind":"run.finished","recorded_at":"t","state":{"run":"finished"}}\n\n'
			);
		}) as unknown as typeof fetch;
		const pulse = new TenantStream();
		const events: string[] = [];
		pulse.subscribe((e) => events.push(e.kind));
		await pulse.open(new URL('https://h.test/x/'), { fetcher, sleep: () => new Promise((r) => setTimeout(r, 5)) });
		expect(requested[0]).toBe('/x/changes?snapshot=position');
		expect(events).toEqual(['snapshot', 'change', 'change']);
		expect(pulse.count).toBe(2);
		expect(pulse.recent.map((c) => c.position)).toEqual(['h2', 'h3']);
		expect(pulse.standing).toBe('refused');
	});
});
