// Ask Taktus (UC-1.14): where an act's links lead, which turn carries which act, and when the
// page asks for the conversation again.

import { describe, expect, it } from 'vitest';
import { actOf, linksOf, nextAsk, waitingForAnswer, type ConversationView, type ProposedAct } from './conversation';

function act(links: Record<string, string>, state: ProposedAct['state'] = 'done'): ProposedAct {
	return {
		id: 'act_1',
		act: 'open_plan',
		arguments: {},
		read_back: 'Open a plan draft.',
		channel: 'channel.web',
		asked_at: '2026-11-14T10:00:00Z',
		state,
		links
	};
}

const view: ConversationView = {
	available: true,
	conversation: 'cnv_1',
	turns: [
		{ at: '2026-11-14T10:00:00Z', channel: 'channel.web', speaker: 'person', text: 'plan it' },
		{ at: '2026-11-14T10:00:01Z', channel: 'channel.web', speaker: 'taktus', text: 'Shall I?', act: 'act_1' }
	],
	acts: [act({}, 'waiting')],
	thinking: null,
	acts_offered: {}
};

describe('an act on the page', () => {
	it('links what it made: a run, a draft, a version, the proposals', () => {
		expect(linksOf(act({ run: 'run_7', process: 'daily' }))).toEqual([
			{ label: 'Run run_7', href: '#/runs/run_7' },
			{ label: 'Proposals of daily', href: '#/changes/daily' }
		]);
		expect(linksOf(act({ draft: 'pd_1' }))).toEqual([{ label: 'Plan draft pd_1', href: '#/plans' }]);
		expect(linksOf(act({ process: 'daily', version: '2' }))).toEqual([
			{ label: 'daily @ 2', href: '#/processes/daily/2' }
		]);
	});

	it('belongs to the turn that proposed it, and to no other', () => {
		expect(actOf(view, view.turns[1]!)?.id).toBe('act_1');
		expect(actOf(view, view.turns[0]!)).toBeUndefined();
	});
});

describe('asking again', () => {
	it('only while a run forms the answer, less often the longer it waits', () => {
		expect(waitingForAnswer(view)).toBe(false);
		expect(waitingForAnswer({ ...view, thinking: 'run_9' })).toBe(true);
		expect(waitingForAnswer(null)).toBe(false);
		expect([0, 1, 2, 3, 9].map(nextAsk)).toEqual([1000, 2000, 4000, 8000, 8000]);
	});
});
