// The processes Taktus proposes in the web app (UC-4.4, ADR-0270): each proposal shows the work
// it would take over, its cost and why now, in the surface's order with the order's reason; one
// drawn from the reader's own work says it is theirs alone; each is accepted or declined on its
// own; and the page is one destination of the navigation.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { currentDestination, DESTINATIONS } from './navigation';
import { act, type ProcessProposals } from './proposed';
import ProposedView from './ProposedView.svelte';

const nothing = () => {};
const LISTED: ProcessProposals = {
	order: 'how often the work recurs per 30 days',
	proposals: [
		{
			id: 'pp_1',
			kind: 'by_hand',
			process_id: 'weekly-report',
			takes_over: 'starting weekly-report by hand, about every 7 days',
			cost: 'per a run: compute_seconds 2; per 30 days: compute_seconds 8.6',
			why_now: 'started by hand 4 times in the last 90 days',
			order: 'recurs 4.3 times per 30 days',
			yours: true
		},
		{
			id: 'pp_2',
			kind: 'healed',
			process_id: 'nightly',
			takes_over: 'removing the cause of a failure of step fetch',
			cost: 'per a run: nothing measured',
			why_now: 'healed 3 times',
			order: 'recurs 3 times per 30 days',
			yours: false
		}
	]
};
const handlers = { onAccept: nothing, onDecline: nothing };

describe('the processes Taktus proposes (UC-4.4)', () => {
	it('shows each proposal with what it takes over, its cost, why now and the order', () => {
		const html = render(ProposedView, { props: { listed: LISTED, ...handlers } }).body;
		expect(html).toContain('Ordered by how often the work recurs per 30 days');
		expect(html).toContain('starting weekly-report by hand, about every 7 days');
		expect(html).toContain('per a run: compute_seconds 2');
		expect(html).toContain('started by hand 4 times in the last 90 days');
		expect(html).toContain('recurs 4.3 times per 30 days');
		expect(html.indexOf('pp_1')).toBeLessThan(html.indexOf('pp_2'));
	});

	it('marks only a proposal drawn from the reader’s own work as theirs alone', () => {
		const html = render(ProposedView, { props: { listed: LISTED, ...handlers } }).body;
		expect(html.match(/data-yours/g)?.length).toBe(1);
	});

	it('says when there is nothing to propose', () => {
		const empty = { ...LISTED, proposals: [] };
		const html = render(ProposedView, { props: { listed: empty, ...handlers } }).body;
		expect(html).toContain('data-empty');
		expect(html).not.toContain('data-proposal');
	});

	it('acts on one proposal at a time', () => {
		expect(act('pp 1', 'accept')).toBe('process-proposals/pp%201/accept');
		expect(act('pp_2', 'decline')).toBe('process-proposals/pp_2/decline');
	});

	it('is a destination of its own', () => {
		expect(currentDestination('/proposed')).toBe('proposed');
		expect(DESTINATIONS.find((d) => d.id === 'proposed')?.href).toBe('#/proposed');
	});
});
