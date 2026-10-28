// What acts for the tenant, what depends on it, and how a process really runs, in the web app
// (ADR-0147, DEC-0218). Each page draws the surface's own answer — `make generate` writes it into
// the fixtures with the reporting component's functions — and nothing else. The stop is asked
// and confirmed by the person before it is sent. No figure names a person (principle 14).

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import {
	deviations,
	registerLine,
	removePath,
	stopAdapter,
	usedText,
	variantsPath,
	wrongResultPath,
	type Register,
	type RemoveView,
	type ResidencyView,
	type VariantsView as Variants,
	type WrongResultView
} from './acting';
import DependenciesView from './DependenciesView.svelte';
import fixtures from './generated/fixtures.json';
import { removeLink, variantsLink, wrongResultLink } from './links';
import RegisterView from './RegisterView.svelte';
import VariantsView from './VariantsView.svelte';

const REGISTER = fixtures.acting.register as unknown as Register;
const REMOVE = fixtures.acting.remove as unknown as RemoveView;
const WRONG = fixtures.acting.wrong_result as unknown as WrongResultView;
const RESIDENCY = fixtures.acting.residency as unknown as ResidencyView;
const VARIANTS = fixtures.acting.variants as unknown as Variants;

function unescape(text: string): string {
	return text.replaceAll('&amp;', '&').replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&lt;', '<').replaceAll('&gt;', '>');
}

describe('the register', () => {
	it('opens with the sentence and shows what needs attention first, with its reasons', () => {
		const html = unescape(render(RegisterView, { props: { register: REGISTER } }).body);
		expect(html).toContain(REGISTER.summary);
		const [first] = REGISTER.rows;
		expect(first!.attention.length).toBeGreaterThan(0);
		for (const reason of first!.attention) expect(html).toContain(reason);
		expect(html.indexOf(`data-adapter="${first!.adapter}"`)).toBeLessThan(
			html.indexOf(`data-adapter="${REGISTER.rows.at(-1)!.adapter}"`)
		);
		for (const row of REGISTER.rows) expect(html).toContain(row.text);
	});

	it('leads from an adapter to what depends on it, and says what it used', () => {
		const html = unescape(render(RegisterView, { props: { register: REGISTER } }).body);
		expect(html).toContain(`href="${removeLink('connector.tickets')}"`);
		expect(html).toContain(usedText(REGISTER.rows[0]!.used));
		expect(html).toContain('outside the rule');
	});

	it('offers the stop only where it can be sent, and names no person', () => {
		const without = unescape(render(RegisterView, { props: { register: REGISTER } }).body);
		expect(without).not.toContain('Stop…');
		const withStop = unescape(
			render(RegisterView, { props: { register: REGISTER, onStop: async () => null } }).body
		);
		expect(withStop).toContain('Stop…');
		expect(withStop).toContain('No row names a person.');
	});

	it('sends the stop of one adapter as the reader, with no reason', async () => {
		const calls: { url: string; init?: RequestInit }[] = [];
		const fetcher = (async (url: URL, init?: RequestInit) => {
			calls.push({ url: String(url), init });
			return new Response(JSON.stringify({ adapter: 'connector.tickets' }), { status: 202 });
		}) as unknown as typeof fetch;
		const answer = await stopAdapter(new URL('https://instance.test/p/'), 'connector.tickets', fetcher);
		expect(answer.ok).toBe(true);
		expect(calls[0]!.url).toBe('https://instance.test/p/register/connector.tickets/stop');
		expect(calls[0]!.init?.method).toBe('POST');
		expect(calls[0]!.init?.body).toBe('{}');
	});

	it('has one line for the start page', () => {
		expect(registerLine(REGISTER)).toBe('2 of 3 adapters need attention.');
	});
});

describe('the dependencies', () => {
	it('split what breaks from what only degrades when an adapter goes', () => {
		const html = unescape(render(DependenciesView, { props: { remove: REMOVE } }).body);
		expect(html).toContain(REMOVE.summary);
		expect(html).toContain('Breaks');
		expect(html).toContain('Only degrades');
		for (const u of [...REMOVE.breaks, ...REMOVE.degrades]) expect(html).toContain(`data-use="${u.process_id}:${u.step_id}"`);
	});

	it('follow a wrong result forward and mark what left the system', () => {
		const html = unescape(render(DependenciesView, { props: { wrong: WRONG } }).body);
		expect(html).toContain(WRONG.summary);
		const left = WRONG.reached.filter((r) => r.left.length);
		expect(left.length).toBe(1);
		expect(html).toContain('egress.delivery');
		expect(html).toContain(WRONG.since_when);
		expect(html).toContain(`href="${wrongResultLink(left[0]!.run_id, left[0]!.step_id)}"`);
	});

	it('show where data goes against the rule', () => {
		const html = unescape(render(DependenciesView, { props: { residency: RESIDENCY } }).body);
		expect(html).toContain(RESIDENCY.summary);
		expect(html).toContain('data-residency="model.writer"');
	});
});

describe('how a process really runs', () => {
	it('shows each variant with its share, the designed path first named as such', () => {
		const html = unescape(render(VariantsView, { props: { view: VARIANTS } }).body);
		expect(html).toContain(VARIANTS.summary);
		for (const v of VARIANTS.variants) expect(html).toContain(v.text);
		expect(VARIANTS.variants[0]!.designed).toBe(true);
		expect(deviations(VARIANTS.variants[1]!)).toEqual([{ what: 'fell_back', step: 'classify' }]);
	});

	it('shows the waiting by cause and the proposals a person decides', () => {
		const html = unescape(render(VariantsView, { props: { view: VARIANTS } }).body);
		expect(html).toContain('data-waiting="approve"');
		for (const p of VARIANTS.proposals) expect(html).toContain(p.text);
		expect(html).toContain('Decide it in a change in dialogue');
		expect(VARIANTS.roles[0]!.text).toContain('accounts-approver');
	});
});

describe('the paths and links', () => {
	it('name each read and each page', () => {
		expect(removePath('connector.a b')).toBe('dependencies/remove/connector.a%20b');
		expect(wrongResultPath('run_1', 'draft')).toBe('dependencies/wrong-result/run_1/draft');
		expect(variantsPath('invoices')).toBe('processes/invoices/variants');
		expect(variantsLink('invoices')).toBe('#/variants/invoices');
		expect(removeLink()).toBe('#/dependencies');
	});
});
