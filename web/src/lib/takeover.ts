// Taking over a running step, and handing its result back, from the run's page (UC-4.19,
// ADR-0128). The page decides nothing: the surface takes the ask, the runner serves it at the
// step's next boundary, and the run level says where every served take-over stands. What only
// the asker knows — that they asked, and under which identifier — is held by the page while it is
// open, so that an ask the runner refused is shown as refused and not silently forgotten. It is
// stored nowhere: a served take-over is on the run level for every reader.

import { read, send, type Answer } from './api';
import { duration } from './duration';
import type { RunLevel, StepElement, TakeoverState } from './types';

/** The step states in which a step is executed, and may be taken over (ADR-0128 §1). */
const IN_FLIGHT = ['admitted', 'running'];

/** A take-over this reader asked for, as the surface answered the ask. */
export interface Asked {
	takeover: string;
	step: string;
}

/** Where a take-over stands for the page: the run level's three, and the two only an asker sees. */
export type Standing = 'asked' | 'refused' | 'held' | 'handed_back' | 'lapsed';

/** The steps that offer "take over": running worker steps of a running run, while no step of
 * the run is held — only the first ask of a run is taken (ADR-0128 §1). */
export function offered(level: RunLevel): StepElement[] {
	if (level.run.state !== 'running') return [];
	if (level.steps.some((s) => s.takeover?.standing === 'held')) return [];
	return level.steps.filter((s) => s.method === 'worker' && IN_FLIGHT.includes(s.state));
}

/** Where the reader's own ask stands. Served, it is what the run level says; not served, it
 * waits while its step still runs, and was refused once the step ended another way. */
export function standingOf(level: RunLevel, asked: Asked): Standing {
	const step = level.steps.find((s) => s.id === asked.step);
	if (step?.takeover?.id === asked.takeover) return step.takeover.standing;
	if (step && IN_FLIGHT.includes(step.state) && level.run.state === 'running') return 'asked';
	return 'refused';
}

/** The steps whose latest take-over is held, handed back, or lapsed, in the run's order. */
export function served(level: RunLevel): StepElement[] {
	return level.steps.filter((s) => s.takeover !== undefined);
}

/** How a result the person wrote is read: a JSON value when it parses as one, else the text as
 * it stands. The reading is shown before anything is handed back (ADR-0008). */
export type Reading = { form: 'json'; value: unknown } | { form: 'text'; value: string };

export function readResult(written: string): Reading | null {
	const trimmed = written.trim();
	if (!trimmed) return null;
	try {
		return { form: 'json', value: JSON.parse(trimmed) as unknown };
	} catch {
		return { form: 'text', value: written };
	}
}

/** The reading in words: what will become the step's result. */
export function described(reading: Reading): string {
	if (reading.form === 'text') {
		const n = reading.value.length;
		return `as text, exactly as you wrote it (${n} character${n === 1 ? '' : 's'})`;
	}
	const value = reading.value;
	if (Array.isArray(value)) return `as a JSON list of ${value.length} value${value.length === 1 ? '' : 's'}`;
	if (value === null) return 'as JSON null: an empty result';
	if (typeof value === 'object') {
		const fields = Object.keys(value as object);
		if (!fields.length) return 'as an empty JSON object';
		return `as a JSON object with the field${fields.length === 1 ? '' : 's'} ${fields.join(', ')}`;
	}
	return `as the JSON ${typeof value} ${JSON.stringify(value)}`;
}

/** Until when the lease runs, in words: the time, and how long is left. */
export function leaseLeft(until: string, now: Date): string {
	const end = new Date(until);
	const left = (end.getTime() - now.getTime()) / 1000;
	const at = `${end.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
	return left > 0 ? `until ${at}, ${duration(left)} left` : `until ${at}; the time has run out`;
}

/** How much of the lease has passed, from 0 to 1, for the bar that shows it. */
export function leasePassed(since: string | undefined, until: string, now: Date): number {
	const end = new Date(until).getTime();
	const start = since ? new Date(since).getTime() : end - 8 * 3600 * 1000;
	if (end <= start) return 1;
	return Math.min(1, Math.max(0, (now.getTime() - start) / (end - start)));
}

/** What the page says about a take-over, by where it stands. */
export function sentence(standing: Standing, step: string): string {
	switch (standing) {
		case 'asked':
			return `You asked to take over ${step}. Its worker stops at its next boundary; then what it reached appears here.`;
		case 'refused':
			return `Your take-over of ${step} was refused: the step ended before its worker stopped, and it was not taken over.`;
		case 'held':
			return `${step} is taken over by a person. No runner executes it until the result is handed back or the time runs out.`;
		case 'handed_back':
			return `The result of ${step} was handed back. It counts as a person's result, with method human.`;
		case 'lapsed':
			return `The take-over of ${step} lapsed: its time ran out without a hand-back, and the step went back to its worker at its checkpoint.`;
	}
}

const runPath = (run: string) => `runs/${encodeURIComponent(run)}`;

/** Asks to take over a running step: `POST /runs/{id}/steps/{step}/takeover`. */
export function askTakeover(base: URL, run: string, step: string, fetcher: typeof fetch = fetch) {
	return send<{ takeover: string; step_id: string; state: string }>(
		base,
		`${runPath(run)}/steps/${encodeURIComponent(step)}/takeover`,
		{},
		fetcher
	);
}

/** The state the step was taken over in, once the take-over is served. */
export function readState(base: URL, run: string, takeover: string, fetcher: typeof fetch = fetch): Promise<Answer<TakeoverState>> {
	return read<TakeoverState>(base, `${runPath(run)}/takeovers/${encodeURIComponent(takeover)}`, fetcher);
}

/** Hands the result back: `POST /runs/{id}/takeovers/{tko}/hand-back`. */
export function handBack(base: URL, run: string, takeover: string, result: unknown, fetcher: typeof fetch = fetch) {
	return send<Record<string, unknown>>(
		base,
		`${runPath(run)}/takeovers/${encodeURIComponent(takeover)}/hand-back`,
		{ result },
		fetcher
	);
}

/** What the page says after a hand-back the surface refused, by its status. */
export function handBackRefused(status: number, detail: string): string {
	if (status === 409) return 'The take-over’s time ran out: the step went back to its worker, and nothing was handed back.';
	if (status === 404) return 'No step is held under this take-over any more: it was handed back, or its time ran out.';
	return detail || 'The result was not handed back.';
}
