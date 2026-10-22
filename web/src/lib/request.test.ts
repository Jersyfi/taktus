// A decision request in the web app (UC-7.4, ADR-0042, ADR-0063 §4 as amended): every part of
// the request is shown, the recommended option is marked, an answer goes to the surface as the
// reader gave it, and nothing takes effect on the page before the reader confirms the reading.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { send } from './api';
import RequestView from './RequestView.svelte';
import type { AddressedRequest } from './types';

const OPEN: AddressedRequest = {
	id: 'dr_1',
	decider: 'owner',
	raised_at: '2026-10-12T09:00:00Z',
	overdue: false,
	answered_by_you: false,
	request: {
		id: 'dr_1',
		raised_by: { run: 'run_1', step: 'accept' },
		class: 'domain',
		situation: 'A contribution proposes a connector.',
		question: 'Keep contribution 318, and in which version?',
		options: [
			{ id: 'A', proposal: 'Keep it in 0.4.0', consequence: '0.4.0 grows by one adapter', recommended: false },
			{ id: 'B', proposal: 'Keep it in 0.5.0', recommended: true, reason: '0.4.0 is full' }
		],
		blocking: ['run_1'],
		due: '2026-10-15',
		status: 'open'
	}
};

const nothing = () => {};

describe('a decision request', () => {
	it('shows every part, marks the recommended option and offers both ways to answer', () => {
		const html = render(RequestView, { props: { addressed: OPEN, onAnswer: nothing, onConfirm: nothing } }).body;
		for (const part of [OPEN.request.question, OPEN.request.situation, 'Keep it in 0.4.0', '0.4.0 is full', 'run_1', '2026-10-15']) {
			expect(html).toContain(part);
		}
		expect(html).toMatch(/data-option="B" class="[^"]*recommended/);
		expect(html).not.toMatch(/data-option="A" class="[^"]*recommended/);
		expect(html).toContain('Choose A');
		expect(html).toContain('Or answer in your own words');
	});

	it('asks for a confirmation of the reading, and offers no answer once it is read', () => {
		const read: AddressedRequest = {
			...OPEN,
			answered_by_you: true,
			reflection: 'You chose B: keep it, in 0.5.0.',
			request: { ...OPEN.request, status: 'interpreted', answer_raw: 'later', answer_interpreted: { option: 'B' } }
		};
		const html = render(RequestView, { props: { addressed: read, onAnswer: nothing, onConfirm: nothing } }).body;
		expect(html).toContain('You chose B: keep it, in 0.5.0.');
		expect(html).toContain('Yes, that is what I mean');
		expect(html).not.toContain('Choose A');
	});

	it('sends the answer as given, with the session cookie and no key', async () => {
		const calls: { url: string; init: RequestInit }[] = [];
		const fetcher = (async (url: URL, init: RequestInit) => {
			calls.push({ url: String(url), init });
			return new Response(JSON.stringify({ message: 'read', request: OPEN }), { status: 200 });
		}) as unknown as typeof fetch;
		const answer = await send(new URL('https://instance.test/p/'), 'decisions/dr_1/answer', { text: 'later' }, fetcher);
		expect(answer.ok).toBe(true);
		expect(calls[0]!.url).toBe('https://instance.test/p/decisions/dr_1/answer');
		expect(calls[0]!.init.method).toBe('POST');
		expect(calls[0]!.init.body).toBe('{"text":"later"}');
		expect(calls[0]!.init.credentials).toBe('same-origin');
		expect((calls[0]!.init.headers as Record<string, string>)['Authorization']).toBeUndefined();
	});
});
