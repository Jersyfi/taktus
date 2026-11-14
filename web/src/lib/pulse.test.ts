// The redesign's promises held in the rendered page (ADR-0321..0323): the Takt is drawn from
// recorded changes only and an idle tenant looks idle; the text equivalent is in the page in the
// picture mode; nothing is listed twice; a failure is said as a failure, never as empty.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ErrorState from './ErrorState.svelte';
import fixtures from './generated/fixtures.json';
import ProcessView from './ProcessView.svelte';
import RunView from './RunView.svelte';
import TaktStrip from './TaktStrip.svelte';
import { isFailure, merged, minutes, taktLine } from './takt';
import { destinationsOf, linesOf, readToday } from './todayData';
import type { Change, ProcessLevel, RunLevel } from './types';

const PROCESS = fixtures.process_level as unknown as ProcessLevel;
const RUN = fixtures.run_level as unknown as RunLevel;
const NOW = Date.parse('2026-11-14T12:00:30Z');

function at(minutesAgo: number, extra: Partial<Change> = {}): Change {
	const when = new Date(NOW - minutesAgo * 60_000).toISOString();
	return { position: `p${minutesAgo}-${extra.kind ?? ''}`, run: 'r1', kind: 'step.finished', recorded_at: when, state: { step: 'succeeded' }, ...extra };
}

function unescape(text: string): string {
	return text.replaceAll('&amp;', '&').replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"').replaceAll('&#39;', "'");
}

function count(haystack: string, needle: string): number {
	return haystack.split(needle).length - 1;
}

describe('the Takt of the last hour', () => {
	it('test_an_idle_tenant_draws_no_motion: no change in the hour, a flat and still strip', () => {
		const drawn = minutes([], NOW);
		expect(drawn).toHaveLength(60);
		expect(drawn.every((m) => m.count === 0)).toBe(true);
		const html = render(TaktStrip, { props: { drawn, arrival: 0, arrivedAt: null } }).body;
		expect(html).toContain('data-motion="none"');
		expect(html).not.toContain('arrived');
		expect(html).not.toContain('data-failed');
		expect(html.match(/<rect class="[^"]*\bquiet\b[^"]*"/g)?.length).toBe(60);
		expect(taktLine(drawn, [], NOW)).toBe('No change was recorded in the last 60 minutes.');
	});

	it('replays nothing from the past as motion: history alone draws still marks', () => {
		const history = [at(50), at(50), at(12, { kind: 'step.failed', state: { step: 'failed' } }), at(3)];
		const drawn = minutes(history, NOW);
		expect(drawn.reduce((n, m) => n + m.count, 0)).toBe(4);
		expect(drawn.reduce((n, m) => n + m.failed, 0)).toBe(1);
		const html = render(TaktStrip, { props: { drawn, arrival: 0, arrivedAt: null } }).body;
		expect(html).toContain('data-motion="none"');
		expect(html).not.toContain('arrived');
		expect(count(html, 'data-failed="1"')).toBe(1);
	});

	it('moves only the minute of a new arrival, once, and nothing where motion is not allowed', () => {
		const changes = [at(30), at(0)];
		const drawn = minutes(changes, NOW);
		const minute = Math.floor(Date.parse(changes[1]!.recorded_at) / 60_000) * 60_000;
		const moving = render(TaktStrip, { props: { drawn, arrival: 1, arrivedAt: minute } }).body;
		expect(count(moving, 'tick arrived')).toBe(1);
		const still = render(TaktStrip, { props: { drawn, arrival: 1, arrivedAt: minute, still: true } }).body;
		expect(still).not.toContain('arrived');
		expect(still).toContain('data-motion="none"');
	});

	it('draws only what was recorded in the hour, each change once', () => {
		const old = at(61);
		const both = merged([at(5), old], [at(5)]);
		expect(both).toHaveLength(2);
		expect(minutes(both, NOW).reduce((n, m) => n + m.count, 0)).toBe(1);
		expect(isFailure(at(1, { kind: 'run.escalated', state: { run: 'escalated' } }))).toBe(true);
		expect(isFailure(at(1))).toBe(false);
	});
});

describe('picture first, text on a switch', () => {
	it('keeps the text equivalent in the page, out of sight, in the picture mode (UC-6.10 §2)', () => {
		const html = unescape(render(ProcessView, { props: { level: PROCESS, motionAllowed: true, mode: 'picture' } }).body);
		expect(html).toMatch(/<section class="text[^"]*sr-only[^"]*"[^>]*aria-label="The process as text"/);
		for (const step of PROCESS.steps) expect(html).toContain(step.text);
		expect(html).toContain('class="tissue');
		expect(html).not.toContain('>As text</h2>');
	});

	it('shows the text in place of the drawing in the text mode', () => {
		const html = unescape(render(ProcessView, { props: { level: PROCESS, motionAllowed: true, mode: 'text' } }).body);
		expect(html).toContain('>As text</h2>');
		expect(html).not.toContain('class="tissue');
		expect(html).not.toMatch(/<section class="text[^"]*sr-only/);
		for (const step of PROCESS.steps) expect(html).toContain(step.text);
	});

	it('offers the switch as two pressed buttons', () => {
		const html = render(RunView, { props: { level: RUN, motionAllowed: true, mode: 'picture' } }).body;
		expect(html).toMatch(/<button[^>]*aria-pressed="true"[^>]*>Picture<\/button>/);
		expect(html).toMatch(/<button[^>]*aria-pressed="false"[^>]*>Text<\/button>/);
	});
});

describe('nothing is listed twice', () => {
	it('lists each run of a version once, in either mode — not again under the text', () => {
		const runs = PROCESS.runs ?? [];
		expect(runs.length).toBeGreaterThan(0);
		for (const mode of ['picture', 'text'] as const) {
			const html = unescape(render(ProcessView, { props: { level: PROCESS, motionAllowed: true, mode } }).body);
			for (const run of runs) {
				expect(count(html, run.text), `${mode}: ${run.id}`).toBe(1);
				expect(count(html, `href="#/runs/${run.id}"`), `${mode}: ${run.id}`).toBe(1);
			}
			expect(count(html, 'Runs of this version')).toBe(1);
		}
	});

	it('says what a run consumed once in the text mode', () => {
		const html = unescape(render(RunView, { props: { level: RUN, motionAllowed: true, mode: 'text' } }).body);
		expect(html).not.toContain('Consumed so far</dt>');
		expect(html).toContain(RUN.run.text);
	});

	it('lists each run of a version once and says how many there are by state', () => {
		const level = { ...PROCESS, counts: { finished: 3, running: 1, waiting_human: 0 } };
		const html = unescape(render(ProcessView, { props: { level, motionAllowed: true, mode: 'picture' } }).body);
		expect(html).toContain('4 in all: 3 finished, 1 running.');
	});
});

describe('a failure is said as a failure', () => {
	it('draws a 5xx as a failure with a way to read again, never as empty', () => {
		const html = render(ErrorState, { props: { what: 'Today', problem: { status: 503, title: 'Service Unavailable', detail: '' }, onRetry: () => {} } }).body;
		expect(html).toContain('role="alert"');
		expect(html).toContain('data-state="failed"');
		expect(html).toContain('503');
		expect(html).toContain('Read again');
		expect(html).not.toContain('data-state="empty"');
	});

	it('answers Today as failed when the surface fails, not as a tenant with nothing', async () => {
		const fetcher = (async () => new Response(JSON.stringify({ status: 503, title: 'Service Unavailable', detail: '' }), { status: 503 })) as unknown as typeof fetch;
		const found = await readToday(new URL('https://h.test/'), fetcher);
		expect(found.ok).toBe(false);
		if (!found.ok) expect(found.problem.status).toBe(503);
	});

	it('takes the surface’s one summary, every count and wait as it answers them (ADR-0318)', async () => {
		const body = {
			overview: fixtures.overview,
			counts: { waiting_for_you: 2, running_now: 1, waiting_on_a_person: 1, failed_last_24h: 0, open_incidents: 0, open_alerts: null },
			waits: [{ kind: 'decision', title: 'Approve?', link: '#/requests/q1', since: '2026-11-14T10:00:00Z', urgent: true }],
			marks: {
				requests: { waiting: 1, overdue: 1 },
				needs: { readable: true, open: 1 },
				autonomy: { below: 0, raises: 0 },
				findings: { readable: false },
				operation: { tenant: 't', incidents: { readable: true, open: 0, total: 0 }, signals: { readable: true, red: 1, yellow: 0, unmeasured: 0, total: 1 }, alerts: { readable: false }, backup: { readable: false }, daily_report: { readable: false } }
			}
		};
		const reads: string[] = [];
		const fetcher = (async (url: URL) => {
			reads.push(new URL(String(url)).pathname);
			return new Response(JSON.stringify(body), { status: 200 });
		}) as unknown as typeof fetch;
		const found = await readToday(new URL('https://h.test/x/'), fetcher);
		expect(reads).toEqual(['/x/levels/today']);
		if (!found.ok) throw new Error('read');
		expect(found.today.counts.waiting_on_a_person).toBe(1);
		expect(found.today.counts.open_alerts).toBeNull();
		expect(found.today.waits[0]).toMatchObject({ link: '#/requests/q1', urgent: true });
		expect(found.today.marks.sort()).toEqual(['needs', 'operation', 'requests']);
		expect(found.today.operation).toBe('Signals needs a look.');
	});

	it('marks nothing and says no line of a kind the reader does not read', () => {
		expect(destinationsOf({})).toEqual([]);
		expect(linesOf({ needs: { readable: false, open: null }, findings: { readable: false } })).toEqual([]);
	});
});
