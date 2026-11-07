// Processes nobody wrote down (UC-9.4, ADR-0245 §2): every record with its stage and the next
// one offered, a pattern found for the reader to agree to, the form that makes a process
// visible, and the interview. Whose a pattern is, is never shown (principle 14).

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import DiscoveriesView from './DiscoveriesView.svelte';
import { mine, nextStage, stageBody, type Discoveries, type Interview } from './discoveries';

const discoveries: Discoveries = {
	discoveries: [
		{ id: 'dsc_1', title: 'Bank reconciliation', origin: 'interview', found: 'Every Friday the open invoices are checked.', stage: 'visible', at: '2026-11-01T00:00:00Z' },
		{ id: 'dsc_2', title: 'Weekly export', origin: 'pattern', found: 'The same export is asked for every week.', stage: 'visible', reader: 'idn_ada', at: '2026-11-02T00:00:00Z' },
		{ id: 'dsc_3', title: 'Dunning', origin: 'request', found: 'Late payers are chased.', stage: 'valued', minutes_by_hand: 20, cases_per_month: 30, at: '2026-11-03T00:00:00Z' }
	]
};
const interview: Interview = {
	mode: 'guided',
	questions: [{ key: 'what', question: 'What is done?', example: 'for example: the open invoices are checked against the bank' }]
};
const noop = () => {};
const handlers = { onDiscover: noop, onMode: noop, onInterview: noop, onAdvance: noop, onAgree: noop };

describe('discovered processes', () => {
	it('offers the stage after a record’s own, and none after automated', () => {
		expect(nextStage('visible')).toBe('documented');
		expect(nextStage('valued')).toBe('decided');
		expect(nextStage('automated')).toBeNull();
	});

	it('takes what the person typed as the surface takes it', () => {
		expect(stageBody('valued', { minutes_by_hand: '20', cases_per_month: ' 30 ' })).toEqual({ minutes_by_hand: 20, cases_per_month: 30 });
		expect(stageBody('automated', { process_id: 'dunning', level: '1', instructions: 'Call them.' })).toEqual({
			process_id: 'dunning',
			level: 1,
			instructions: 'Call them.'
		});
		expect(stageBody('documented', { description: '' })).toEqual({});
	});

	it('knows a pattern found for the reader, and never shows whose it is', () => {
		expect(discoveries.discoveries.map(mine)).toEqual([false, true, false]);
		const { body } = render(DiscoveriesView, { props: { discoveries, interview, ...handlers } });
		expect(body).toContain('3 processes brought to light.');
		expect(body).toContain('Agree it becomes the organisation');
		expect(body).toContain('only you see it until you agree');
		expect(body).toContain('Take it to documented');
		expect(body).toContain('Take it to decided');
		expect(body).toContain('automate');
		expect(body).toContain('Make it visible');
		expect(body).not.toMatch(/idn_/);
	});

	it('asks the interview’s questions, with their examples when guided', () => {
		const { body } = render(DiscoveriesView, {
			props: { discoveries, interview, interviewed: { description: 'What: checks\nWhen: Fridays', owner_role: 'accounting' }, ...handlers }
		});
		expect(body).toContain('What is done?');
		expect(body).toContain('for example: the open invoices');
		expect(body).toContain('aria-pressed="true"');
		expect(body).toContain('Written down');
		expect(body).toContain('Responsible role: accounting');
	});
});
