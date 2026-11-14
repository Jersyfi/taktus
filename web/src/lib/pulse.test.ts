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
import { readToday, forgetServed, waitsOf } from './todayData';
import type { AddressedRequest, Change, ProcessLevel, RunLevel } from './types';
import type { ReportView } from './reports';

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

	it('lists a wait once, whether it comes as a request or as a report', () => {
		const request = { id: 'q1', overdue: false, request: { question: 'Approve the refund?', due: '2026-11-20' } } as unknown as AddressedRequest;
		const report = (id: string, due: string) => ({ id, kind: 'need', title: `Need ${id}`, due, state: 'open', raised_at: '2026-11-01' }) as unknown as ReportView;
		const waits = waitsOf([request], [report('q1', '2026-11-20'), report('n1', '2026-11-15'), { ...report('n2', '2026-11-10'), state: 'filed' } as ReportView]);
		expect(waits.map((w) => w.id)).toEqual(['n1', 'q1']);
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
		forgetServed();
		const fetcher = (async () => new Response(JSON.stringify({ status: 503, title: 'Service Unavailable', detail: '' }), { status: 503 })) as unknown as typeof fetch;
		const found = await readToday(new URL('https://h.test/'), null, fetcher);
		expect(found.ok).toBe(false);
		if (!found.ok) expect(found.problem.status).toBe(503);
	});

	it('names the part of Today whose read failed, and counts nothing it did not read', async () => {
		forgetServed();
		const overview = fixtures.overview;
		const fetcher = (async (url: URL) => {
			const path = new URL(String(url)).pathname;
			if (path === '/levels/today') return new Response('{}', { status: 404 });
			if (path === '/levels/overview') return new Response(JSON.stringify(overview), { status: 200 });
			if (path === '/operation') return new Response('{}', { status: 500 });
			if (path === '/decisions') return new Response(JSON.stringify({ requests: [], overdue: 0 }), { status: 200 });
			if (path === '/owner/reports') return new Response(JSON.stringify({ reports: [] }), { status: 200 });
			return new Response('{}', { status: 403 });
		}) as unknown as typeof fetch;
		const found = await readToday(new URL('https://h.test/'), null, fetcher);
		expect(found.ok).toBe(true);
		if (!found.ok) return;
		expect(found.today.source).toBe('composed');
		expect(found.today.failed).toEqual(['what keeps the operation running']);
		expect(found.today.counts.incidents).toBeNull();
		expect(found.today.counts.waiting_for_you).toBe(0);
		expect(found.today.counts.failed_24h).toBeNull();
	});

	it('takes the surface’s one summary where it is served', async () => {
		forgetServed();
		const body = {
			overview: fixtures.overview,
			counts: { waiting_for_you: 2, running: 1, waiting_on_person: 1, failed_24h: 0, incidents: 0, alerts: 0 },
			waits: [{ id: 'q1', kind: 'decision', title: 'Approve?', due: null, overdue: true }],
			waits_total: 2,
			marks: ['requests'],
			lines: [{ kind: 'requests', href: '#/requests', text: 'Decision requests: 2 wait for you.', waiting: true }]
		};
		const reads: string[] = [];
		const fetcher = (async (url: URL) => {
			reads.push(new URL(String(url)).pathname);
			return new Response(JSON.stringify(body), { status: 200 });
		}) as unknown as typeof fetch;
		const found = await readToday(new URL('https://h.test/'), null, fetcher);
		expect(reads).toEqual(['/levels/today']);
		expect(found.ok && found.today.counts.waiting_on_person).toBe(1);
		expect(found.ok && found.today.waits[0]?.href).toBe('#/requests/q1');
	});
});
