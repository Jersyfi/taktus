// What Taktus took off the reader (UC-13.5, ADR-0245 §1): the surface's sentence, each process
// with its runs, minutes by hand, hours regained as hours and minutes and its takeover
// instructions, the goals reached or not; and the reader's own settings. Only the reader sees it
// unless they share it; nothing scores, ranks or compares a person (principle 14).

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { hoursAndMinutes } from './duration';
import { goalLine, regained, reliefLine, settingsOf, type OwnRelief } from './relief';
import ReliefSection from './ReliefSection.svelte';

const relief: OwnRelief = {
	since: '2026-10-08T00:00:00Z',
	until: '2026-11-07T00:00:00Z',
	processes: [
		{ process: 'invoice', runs_finished: 12, minutes_by_hand: 5, hours_regained: 1, takeover: 'processes/invoice/takeover', roles: ['accounting'] },
		{ process: 'dunning', runs_finished: 1, minutes_by_hand: null, hours_regained: null, takeover: 'processes/dunning/takeover', roles: ['accounting'] }
	],
	hours_regained: 1,
	hours_this_week: 3.5,
	goals: [
		{ title: 'Friday free', hours_per_week: 1, hours_this_week: 3.5, reached: true },
		{ title: 'Monday free', hours_per_week: 8, hours_this_week: 3.5, reached: false }
	],
	shared_with: [],
	sentence: 'Taktus took 13 cases off your roles: 1 h 0 min regained.'
};

describe('what Taktus took off you', () => {
	it('writes hours as hours and minutes, as the surface does', () => {
		expect(hoursAndMinutes(3.5)).toBe('3 h 30 min');
		expect(hoursAndMinutes(1)).toBe('1 h 0 min');
		expect(hoursAndMinutes(0.25)).toBe('15 min');
		expect(regained(null)).toBe('no time by hand is stated');
	});

	it('says each process and each goal in words, a goal reached or not', () => {
		expect(reliefLine(relief.processes[0]!)).toBe('invoice: 12 runs finished, 5 min by hand a case, 1 h 0 min regained.');
		expect(reliefLine(relief.processes[1]!)).toBe('dunning: 1 run finished, minutes by hand not stated, no time by hand is stated regained.');
		expect(goalLine(relief.goals[0]!)).toBe('Friday free: 1 h 0 min a week, 3 h 30 min this week — reached.');
		expect(goalLine(relief.goals[1]!)).toContain('not reached yet');
	});

	it('shows the sentence, the takeover links and that only the reader sees it, and no score', () => {
		const { body } = render(ReliefSection, { props: { relief, onSave: () => {} } });
		expect(body).toContain(relief.sentence);
		expect(body).toContain('Only you see this unless you share it.');
		expect(body).toContain('href="../processes/invoice/takeover"');
		expect(body).toContain('1 h 0 min regained');
		expect(body).toContain('data-reached="true"');
		expect(body).toContain('Once a week');
		for (const word of ['score', 'rank', 'points', 'badge', 'streak', 'level']) expect(body.toLowerCase()).not.toContain(word);
		expect(body).not.toMatch(/idn_/);
	});

	it('reads the settings a person typed', () => {
		expect(settingsOf(' controlling, finance ,', [{ title: 'Friday free', hours: '1.5' }, { title: '', hours: '' }], 'week')).toEqual({
			ok: true,
			settings: { shared_with: ['controlling', 'finance'], goals: [{ title: 'Friday free', hours_per_week: 1.5 }], line: 'week' }
		});
		expect(settingsOf('', [{ title: 'x', hours: 2 }], 'never')).toEqual({
			ok: true,
			settings: { shared_with: [], goals: [{ title: 'x', hours_per_week: 2 }], line: 'never' }
		});
		expect(settingsOf('', [{ title: 'Friday free', hours: '0' }], 'day')).toEqual({ ok: false, problem: 'Goal 1 needs hours a week above zero.' });
		expect(settingsOf('', [{ title: '', hours: '3' }], 'day')).toEqual({ ok: false, problem: 'Goal 1 has no title.' });
	});
});
