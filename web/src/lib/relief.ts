// What Taktus took off the reader, as the surface answers it for them alone (UC-13.5, ADR-0245
// §1): `GET /me/relief`, and the reader's own settings, `PUT /me/relief/settings`. Success is
// time and the goals the reader set: no points, levels, streaks, ranks or comparisons
// (principle 14). Nothing here computes a figure; the hours are the surface's, only written as
// hours and minutes.

import { hoursAndMinutes } from './duration';

export interface Relieved {
	process: string;
	runs_finished: number;
	minutes_by_hand?: number | null;
	hours_regained?: number | null;
	/** The surface's path of the process's takeover instructions. */
	takeover: string;
	roles: string[];
}

export interface GoalReached {
	title: string;
	hours_per_week: number;
	hours_this_week: number;
	reached: boolean;
}

/** `GET /me/relief`. */
export interface OwnRelief {
	since: string;
	until: string;
	processes: Relieved[];
	hours_regained: number;
	hours_this_week: number;
	goals: GoalReached[];
	shared_with: string[];
	sentence: string;
}

export type Line = 'never' | 'day' | 'week';
export const LINES: { id: Line; label: string }[] = [
	{ id: 'never', label: 'Never' },
	{ id: 'day', label: 'Once a day' },
	{ id: 'week', label: 'Once a week' }
];

/** The body of `PUT /me/relief/settings`. */
export interface ReliefSettings {
	shared_with: string[];
	goals: { title: string; hours_per_week: number }[];
	line: Line;
}

/** Hours regained, as the person reads them, or why there is no figure. */
export function regained(hours: number | null | undefined): string {
	if (hours === null || hours === undefined) return 'no time by hand is stated';
	return hoursAndMinutes(hours);
}

/** One process in words. */
export function reliefLine(p: Relieved): string {
	const byHand =
		p.minutes_by_hand === null || p.minutes_by_hand === undefined
			? 'minutes by hand not stated'
			: `${p.minutes_by_hand.toLocaleString('en', { maximumFractionDigits: 1 })} min by hand a case`;
	return `${p.process}: ${p.runs_finished} ${p.runs_finished === 1 ? 'run' : 'runs'} finished, ${byHand}, ${regained(p.hours_regained)} regained.`;
}

/** One goal in words: reached or not, never a score. */
export function goalLine(g: GoalReached): string {
	const state = g.reached ? 'reached' : 'not reached yet';
	return `${g.title}: ${hoursAndMinutes(g.hours_per_week)} a week, ${hoursAndMinutes(g.hours_this_week)} this week — ${state}.`;
}

/** The settings a person typed, read: roles separated by commas, one goal a row with its hours.
 * A row with a title but no positive hours says which, before anything is sent. */
export function settingsOf(
	roles: string,
	goals: { title: string; hours: string | number | null }[],
	line: Line
): { ok: true; settings: ReliefSettings } | { ok: false; problem: string } {
	const shared_with = roles
		.split(',')
		.map((r) => r.trim())
		.filter(Boolean);
	const kept: ReliefSettings['goals'] = [];
	for (const [i, g] of goals.entries()) {
		const title = g.title.trim();
		const typed = String(g.hours ?? '').trim();
		if (!title && !typed) continue;
		const hours = typed ? Number(typed) : NaN;
		if (!title) return { ok: false, problem: `Goal ${i + 1} has no title.` };
		if (!Number.isFinite(hours) || hours <= 0)
			return { ok: false, problem: `Goal ${i + 1} needs hours a week above zero.` };
		kept.push({ title, hours_per_week: hours });
	}
	return { ok: true, settings: { shared_with, goals: kept, line } };
}
