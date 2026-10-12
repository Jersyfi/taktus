// The reader's own page (ADR-0015, principle 14): the reader's own times as handed over, the
// rest only aggregated, a withheld aggregate shown as withheld, and nothing computed on the page.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { duration } from './duration';
import type { ResponseTimes } from './types';
import YoursView from './YoursView.svelte';

const TIMES: ResponseTimes = {
	reader: 'idn_ada',
	own: [
		{ request_id: 'dr_1', run_id: 'run_1', seconds: 7200 },
		{ request_id: 'dr_2', run_id: 'run_2', seconds: 1800 }
	],
	own_total_seconds: 9000,
	own_median_seconds: 4500,
	by_role: [{ group: 'owner', withheld: 'fewer than 2 deciders' }],
	by_department: [{ group: 'finance', decisions: 4, median_seconds: 3000 }]
};

describe('your own page', () => {
	it('opens with how long runs waited on your decisions, as handed over', () => {
		const html = render(YoursView, { props: { times: TIMES } }).body;
		expect(html).toContain('Runs waited 2 h 30 min on your decisions.');
		expect(html).toContain('Your median time to answer: 1 h 15 min.');
		expect(html).toContain('dr_1');
		expect(html).toContain('Only you see this page.');
	});

	it('shows the rest only aggregated, and a withheld aggregate as withheld', () => {
		const html = render(YoursView, { props: { times: TIMES } }).body;
		expect(html).toContain('withheld: fewer than 2 deciders');
		expect(html).toContain('median 50 min over 4 decisions');
	});

	it('says so when no run waited on you', () => {
		const html = render(YoursView, { props: { times: { reader: 'idn_ada' } } }).body;
		expect(html).toContain('No run has waited on a decision of yours.');
	});

	it('reads a duration as a person does', () => {
		expect([duration(42), duration(600), duration(3600), duration(5400), duration(3 * 86400)]).toEqual([
			'42 s',
			'10 min',
			'1 h',
			'1 h 30 min',
			'3 days'
		]);
	});
});
