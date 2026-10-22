// The reports to the owner in the web app (UC-6.11, DEC-0218, ADR-0120): a report's page shows
// what the channel showed and how to answer, nothing takes effect before the reader confirms the
// reading, and the start page lists the open reports newest first, each linking to its page.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { read } from './api';
import { reportLink } from './links';
import OpenReports from './OpenReports.svelte';
import ReportPage from './ReportPage.svelte';
import { openLine, openReports, type ReportView } from './reports';

const NEED: ReportView = {
	id: 'need_0001',
	kind: 'need',
	title: 'A token for the live test',
	needed: ['A token in the environment `live`.'],
	steps: ['Create it.', 'Store it.'],
	standing_still: ['The live test.'],
	due: '2026-10-29',
	offered: [{ id: 'done', label: 'erledigt' }],
	links: [{ label: 'Issue', url: 'https://repository.example/issues/146' }],
	raised_at: '2026-10-22T08:00:00+00:00',
	state: 'open',
	history: [{ at: '2026-10-22T08:00:00+00:00', event: 'raised', by_you: false }]
};

const ALERT: ReportView = {
	...NEED,
	id: 'backup-missing',
	kind: 'failure',
	title: 'No backup since yesterday',
	raised_at: '2026-10-22T09:00:00+00:00'
};

const DECISION: ReportView = {
	...NEED,
	id: 'dr_0001',
	kind: 'decision',
	title: 'Run run_1 has reached step release',
	offered: [
		{ id: 'A', label: 'Release it.', recommended: true },
		{ id: 'B', label: 'Do not release it.' }
	],
	raised_at: '2026-10-21T08:00:00+00:00'
};

const FILED: ReportView = {
	...NEED,
	id: 'need_0000',
	state: 'filed',
	raised_at: '2026-10-22T10:00:00+00:00',
	filed: { answer: 'done', at: '2026-10-22T11:00:00+00:00', where: 'web', by_you: true }
};

const nothing = () => {};

describe("a report's page", () => {
	it('shows what the channel showed: title, what is needed, steps, what stands still, by when', () => {
		const html = render(ReportPage, { props: { report: NEED, onAnswer: nothing, onConfirm: nothing } }).body;
		for (const part of [NEED.title, NEED.needed[0]!, 'Create it.', 'Store it.', 'The live test.', '2026-10-29', 'Needs request']) {
			expect(html).toContain(part);
		}
		expect(html).toContain('https://repository.example/issues/146');
		expect(html).toMatch(/<h1[^>]*>A token for the live test<\/h1>/);
	});

	it('offers every answer the channel offers, marks the recommended one, and takes the reader\'s words', () => {
		const html = render(ReportPage, { props: { report: DECISION, onAnswer: nothing, onConfirm: nothing } }).body;
		expect(html).toContain('Answer: Release it.');
		expect(html).toContain('Answer: Do not release it.');
		expect(html).toMatch(/data-offered="A" class="[^"]*recommended/);
		expect(html).toContain('Or answer in your own words');
	});

	it('reflects the reading back and asks for a confirmation before anything is filed', () => {
		const read: ReportView = {
			...NEED,
			state: 'reflected',
			reading: { answer: 'done', kept: false, at: '2026-10-22T08:05:00+00:00', by_you: true }
		};
		const html = render(ReportPage, {
			props: { report: read, message: 'Ich habe deine Antwort als „erledigt“ gelesen.', onAnswer: nothing, onConfirm: nothing }
		}).body;
		expect(html).toContain('Ich habe deine Antwort als „erledigt“ gelesen.');
		expect(html).toContain('Yes, that is what I mean');
		expect(html).toContain('Nothing is filed before you confirm');
		expect(html).not.toContain('Answer: erledigt');
	});

	it('shows a filed answer and offers no other', () => {
		const html = render(ReportPage, { props: { report: FILED, onAnswer: nothing, onConfirm: nothing } }).body;
		expect(html).toContain('Filed: erledigt');
		expect(html).toContain('answered by you, and filed');
		expect(html).not.toContain('Answer: erledigt');
	});

	it('is read with the key in the header, from the surface beside the app', async () => {
		const calls: { url: string; init: RequestInit }[] = [];
		const fetcher = (async (url: URL, init: RequestInit) => {
			calls.push({ url: String(url), init });
			return new Response(JSON.stringify(NEED), { status: 200 });
		}) as unknown as typeof fetch;
		const answer = await read<ReportView>(new URL('https://instance.test/p/'), 'owner/reports/need_0001', 'k', fetcher);
		expect(answer.ok).toBe(true);
		expect(calls[0]!.url).toBe('https://instance.test/p/owner/reports/need_0001');
		expect((calls[0]!.init.headers as Record<string, string>)['Authorization']).toBe('Bearer k');
	});

	it('lives where the control plane links it', () => {
		expect(reportLink('need_0001')).toBe('#/reports/need_0001');
		expect(reportLink('need 0002/a')).toBe('#/reports/need%200002%2Fa');
	});
});

describe("the start page's reports", () => {
	it('lists the open reports and alerts newest first, without the filed ones', () => {
		expect(openReports([DECISION, NEED, FILED, ALERT]).map((r) => r.id)).toEqual(['backup-missing', 'need_0001', 'dr_0001']);
	});

	it('says how many are open', () => {
		expect(openLine(0)).toBe('No report waits for an answer.');
		expect(openLine(1)).toBe('1 report waits for an answer.');
		expect(openLine(3)).toBe('3 reports wait for an answer.');
	});

	it('links each open report to its page, under a line that counts them', () => {
		const html = render(OpenReports, { props: { key: 'k', reports: [DECISION, NEED, FILED, ALERT] } }).body;
		expect(html).toContain('3 reports wait for an answer.');
		const links = [...html.matchAll(/href="([^"]+)"/g)].map((m) => m[1]);
		expect(links).toEqual(['#/reports/backup-missing', '#/reports/need_0001', '#/reports/dr_0001']);
		expect(html).toContain('Failure');
		expect(html).not.toContain('need_0000');
	});
});
