// What governs the work in the web app (ADR-0122, DEC-0218). Each page draws the surface's own
// answer — `make generate` writes it into the fixtures with the surface's functions — and nothing
// else. The start page has one line per kind. An answer in review is read back before anything
// is done (ADR-0008). No figure names a person (principle 14, ADR-0015).

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import AutonomyView from './AutonomyView.svelte';
import FindingsView from './FindingsView.svelte';
import fixtures from './generated/fixtures.json';
import {
	AUTONOMY,
	confirmReading,
	FINDINGS,
	governanceLines,
	NEEDS,
	needsOf,
	readBack,
	TENANTS,
	writeTenant,
	type AutonomyAnswer,
	type FindingsAnswer,
	type OwnerReport,
	type ReviewReading,
	type Tenant
} from './governance';
import GovernanceLines from './GovernanceLines.svelte';
import NeedsView from './NeedsView.svelte';
import TenantsView from './TenantsView.svelte';

const AUTONOMY_ANSWER = fixtures.governance.autonomy as unknown as AutonomyAnswer;
const FINDINGS_ANSWER = fixtures.governance.findings as unknown as FindingsAnswer;
const REPORTS = fixtures.governance.reports.reports as unknown as OwnerReport[];
const TENANT_LIST = fixtures.governance.tenants.tenants as unknown as Tenant[];
const nothing = () => {};

function unescape(text: string): string {
	return text.replaceAll('&amp;', '&').replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&lt;', '<').replaceAll('&gt;', '>');
}

type Call = { url: string; init?: RequestInit };

/** A surface that answers each path as given, and records every call. */
function surface(answers: Record<string, { status: number; body: unknown }>, calls: Call[] = []): typeof fetch {
	return (async (url: URL, init?: RequestInit) => {
		calls.push({ url: String(url), init });
		const path = new URL(String(url)).pathname.replace(/^\/p\//, '');
		const found = answers[path] ?? { status: 404, body: { status: 404, title: 'Not found', detail: '' } };
		return new Response(JSON.stringify(found.body), { status: found.status });
	}) as unknown as typeof fetch;
}

const BASE = new URL('https://instance.test/p/');

describe('the levels and corrections', () => {
	it('opens with the sentence, and shows the level in force, the stated one and why', () => {
		const html = unescape(render(AutonomyView, { props: { answer: AUTONOMY_ANSWER } }).body);
		const [process] = AUTONOMY_ANSWER.processes;
		expect(html).toContain(AUTONOMY_ANSWER.summary);
		expect(html).toContain(process!.text);
		expect(html).toContain(process!.stated_text);
		expect(html).toMatch(/data-level="1"/);
		expect(html).toContain('Fell from 2 to 1 by the rule <code>corrections.rate</code>');
	});

	it('shows the rates per process and per action class, over 7 and 28 days', () => {
		const html = unescape(render(AutonomyView, { props: { answer: AUTONOMY_ANSWER } }).body);
		expect(html).toContain('data-unit="process"');
		expect(html).toContain('data-unit="mail.send"');
		expect(html).toContain('3 of 4 changed · 75 %');
		expect(html).toContain('3 of 12 changed · 25 %');
		expect(html).toContain('nothing decided in 7 days');
		for (const unit of AUTONOMY_ANSWER.processes[0]!.units) expect(html).toContain(unit.text);
	});

	it('names no person: the surface hands no field for one, and the page adds none', () => {
		const fields = JSON.stringify(AUTONOMY_ANSWER);
		for (const word of ['"actor"', '"by"', '"person"', '"identity"', '"decider"']) expect(fields).not.toContain(word);
		const html = render(AutonomyView, { props: { answer: AUTONOMY_ANSWER } }).body;
		expect(html).toContain('No figure names a person.');
	});
});

describe('the findings', () => {
	it('shows each lack with its classification and the words it would leave in', () => {
		const html = unescape(render(FindingsView, { props: { answer: FINDINGS_ANSWER, onAnswer: nothing, onConfirm: nothing } }).body);
		expect(html).toContain(FINDINGS_ANSWER.summary);
		expect(html).toContain('data-kind="product"');
		expect(html).toContain('data-kind="configuration"');
		expect(html).toContain('Configure coder, which the release ships.');
		expect(html).toContain('Exactly what would leave');
		for (const f of FINDINGS_ANSWER.findings) expect(html).toContain(f.said);
	});

	it('offers the three answers only for a candidate in review', () => {
		const html = render(FindingsView, { props: { answer: FINDINGS_ANSWER, onAnswer: nothing, onConfirm: nothing } }).body;
		const [candidate, local] = FINDINGS_ANSWER.findings;
		expect(html).toContain(`data-review="${candidate!.lack.key}"`);
		expect(html).not.toContain(`data-review="${local!.lack.key}"`);
		for (const label of ['Send it', 'Not now', 'Local for us']) expect(html).toContain(label);
	});

	it('shows the reading and asks for a confirmation before anything is done', () => {
		const lack = FINDINGS_ANSWER.findings[0]!.lack.key;
		const reading: ReviewReading = { lack, answer: 'send', reading: 'You answer send: it leaves now.', text: 'x', confirmation: 'c'.repeat(64) };
		const html = render(FindingsView, { props: { answer: FINDINGS_ANSWER, reading, onAnswer: nothing, onConfirm: nothing } }).body;
		expect(html).toContain('You answer send: it leaves now.');
		expect(html).toContain('Yes, do it');
		expect(html).toContain('Nothing is done before you confirm.');
		expect(html).not.toContain('Send it');
	});

	it('reads an answer back first, and confirms exactly what was read back', async () => {
		const calls: Call[] = [];
		const reading: ReviewReading = { lack: 'abc', answer: 'local', reading: 'r', text: 't', confirmation: 'd'.repeat(64) };
		const fetcher = surface(
			{
				'findings/abc/review': { status: 200, body: reading },
				'findings/abc/review/confirm': { status: 200, body: { done: true, answer: 'local', message: 'Remembered.' } }
			},
			calls
		);
		const back = await readBack(BASE, 'k', 'abc', 'local', fetcher);
		expect(back.ok && back.body.confirmation).toBe(reading.confirmation);
		expect(calls.map((c) => c.url)).toEqual(['https://instance.test/p/findings/abc/review']);
		expect(calls[0]!.init?.body).toBe('{"answer":"local"}');

		const done = await confirmReading(BASE, 'k', reading, true, fetcher);
		expect(done.ok && done.body.message).toBe('Remembered.');
		expect(calls[1]!.url).toBe('https://instance.test/p/findings/abc/review/confirm');
		expect(JSON.parse(String(calls[1]!.init?.body))).toEqual({ answer: 'local', confirmation: reading.confirmation, confirmed: true });
		expect((calls[1]!.init?.headers as Record<string, string>)['Authorization']).toBe('Bearer k');
	});
});

describe('the needs', () => {
	it('shows each need with what is needed, the steps, what stands still, by when and its state', () => {
		const needs = needsOf(REPORTS);
		const html = unescape(render(NeedsView, { props: { needs } }).body);
		const [need] = needs;
		expect(html).toContain('1 need is open.');
		for (const part of [need!.title, ...need!.needed, ...need!.steps, ...need!.standing_still, need!.due]) expect(html).toContain(part);
		expect(html).toContain('data-state="open"');
		expect(html).toContain('href="#/requests"');
	});

	it('takes the needs out of the reports, and only them', () => {
		const decision = { ...REPORTS[0]!, id: 'dr_1', kind: 'decision' };
		expect(needsOf([...REPORTS, decision]).map((n) => n.id)).toEqual([REPORTS[0]!.id]);
	});
});

describe('the tenants', () => {
	it('lists each tenant with its identifier and its name', () => {
		const html = unescape(render(TenantsView, { props: { tenants: TENANT_LIST, onCreate: nothing, onRename: nothing } }).body);
		expect(html).toContain('This instance serves 2 tenants.');
		for (const t of TENANT_LIST) {
			expect(html).toContain(t.id);
			expect(html).toContain(t.name);
		}
		expect(html).toContain('An account key is not admitted here.');
	});

	it('creates with the administration key and a name, never an identifier', async () => {
		const calls: Call[] = [];
		const fetcher = surface({ 'administration/tenants': { status: 201, body: TENANT_LIST[1] } }, calls);
		const created = await writeTenant(BASE, 'adm', 'Acme Software', null, fetcher);
		expect(created.ok).toBe(true);
		expect(calls[0]!.init?.method).toBe('POST');
		expect(calls[0]!.init?.body).toBe('{"name":"Acme Software"}');
		expect((calls[0]!.init?.headers as Record<string, string>)['Authorization']).toBe('Bearer adm');
	});
});

describe('the start page', () => {
	const answers = {
		decisions: { status: 200, body: { identity: 'idn_ada', requests: [{}, {}], overdue: 1 } },
		'owner/reports': { status: 200, body: fixtures.governance.reports },
		autonomy: { status: 200, body: AUTONOMY_ANSWER },
		findings: { status: 200, body: FINDINGS_ANSWER },
		'administration/tenants': { status: 200, body: fixtures.governance.tenants }
	};

	it('has one line per kind, each saying how many wait and leading to its page', async () => {
		const lines = await governanceLines(BASE, 'k', 'adm', surface(answers));
		expect(lines.map((l) => [l.kind, l.href])).toEqual([
			['requests', '#/requests'],
			['needs', NEEDS],
			['autonomy', AUTONOMY],
			['findings', FINDINGS],
			['tenants', TENANTS]
		]);
		expect(lines.map((l) => l.text)).toEqual([
			'Decision requests: 2 wait for you, 1 past its date.',
			'Needs: 1 is open.',
			'Levels and corrections: 1 process runs below the stated level.',
			'Findings: 2 lacks met, 1 waits for a review.',
			'Tenants: this instance serves 2.'
		]);
		const html = render(GovernanceLines, { props: { lines } }).body;
		for (const line of lines) expect(html).toContain(`href="${line.href}"`);
		expect(html).toContain('data-line="needs"');
	});

	it('leaves out a kind the surface refuses the reader', async () => {
		const refused = { status: 403, body: { status: 403, title: 'Forbidden', detail: 'only the owner' } };
		const lines = await governanceLines(BASE, 'k', null, surface({ ...answers, 'owner/reports': refused, findings: refused }));
		expect(lines.map((l) => l.kind)).toEqual(['requests', 'autonomy', 'tenants']);
		expect(lines.at(-1)!.text).toBe('Tenants: for the holder of the administration key.');
	});
});
