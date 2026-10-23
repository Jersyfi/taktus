// The trace inside a worker's step, on the run's page (UC-6.14, ADR-0135).
//
// The trace is content, kept outside the ledger, so the stream of changes does not carry it
// (ADR-0055). The page asks for the lines after the last one it holds, again every two seconds
// while the step is in flight: a line the worker reported is on the page within the five
// seconds the use case allows. Once the step ended, the page asks no more. A share names a
// role, never a person: the surface hands back the link, and only an identity holding that
// role opens it.

import { read, type Answer } from './api';
import type { RunLevel, StepElement, TraceLine, TraceView } from './types';

/** How long the page waits before it asks again while the step is in flight. */
export const ASK_AGAIN_MS = 2000;

/** What a role looks like: a lowercase token, as the ledger records it. */
export const ROLE = /^[a-z][a-z0-9_]*$/;

/** The steps that may hold a trace: a worker's, and one a person took over from its worker. */
export function traced(level: RunLevel): StepElement[] {
	return level.steps.filter((s) => s.method === 'worker' || (s.method === 'human' && s.takeover));
}

/** The step shown first: the one named, else a worker step in flight, else the last one. */
export function focused(level: RunLevel, named?: string): string | null {
	const steps = traced(level);
	if (named && steps.some((s) => s.id === named)) return named;
	const flying = steps.find((s) => s.state === 'running' || s.state === 'admitted');
	return flying?.id ?? steps.at(-1)?.id ?? null;
}

/** The surface's path of a step's trace after a position. */
export function tracePath(runId: string, stepId: string, after = 0): string {
	const path = `levels/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}/trace`;
	return after > 0 ? `${path}?after=${after}` : path;
}

/** The lines held, with those just read after them; a line held already is not added twice. */
export function merged(held: TraceLine[], read: TraceLine[] | undefined): TraceLine[] {
	const last = held.at(-1)?.position ?? 0;
	return [...held, ...(read ?? []).filter((line) => line.position > last)];
}

/** The link a share hands on, as an address: the surface's, with the trace's route. */
export function shareAddress(base: URL, link: string): string {
	return new URL(link, base).toString();
}

/** The form a line is drawn with: one per kind of event, refused calls apart from made ones. */
export type Mark = 'start' | 'say' | 'call' | 'refused' | 'choice' | 'use' | 'boundary' | 'made' | 'end' | 'reach';

export function markOf(line: TraceLine): Mark {
	switch (line.type) {
		case 'step.started':
			return 'start';
		case 'step.progress':
			return 'say';
		case 'tool.called':
			return line.detail?.refused ? 'refused' : 'call';
		case 'decision.made':
			return 'choice';
		case 'consumption.reported':
			return 'use';
		case 'step.boundary':
			return 'boundary';
		case 'artifact.produced':
			return 'made';
		case 'assignment.finished':
			return 'end';
		default:
			return 'reach';
	}
}

/** The time of a line, as the reader's clock shows it. */
export function clockOf(ts: string): string {
	const at = new Date(ts);
	return Number.isNaN(at.getTime()) ? ts : at.toLocaleTimeString([], { hour12: false });
}

export interface FollowTrace {
	base: URL;
	runId: string;
	stepId: string;
	signal: AbortSignal;
	onTrace: (trace: TraceView, lines: TraceLine[]) => void;
	onAbsent: () => void;
	onRefused: () => void;
	fetcher?: typeof fetch;
	sleep?: (ms: number) => Promise<void>;
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
	return new Promise((resolve) => {
		const timer = setTimeout(resolve, ms);
		signal.addEventListener('abort', () => {
			clearTimeout(timer);
			resolve();
		});
	});
}

/** Reads the trace, and again after the last line while it is open, until the signal aborts.
 * A reader the surface refuses, or a trace they may not see, ends it. */
export async function followTrace(options: FollowTrace): Promise<void> {
	const sleep = options.sleep ?? ((ms: number) => delay(ms, options.signal));
	let lines: TraceLine[] = [];
	let after = 0;
	while (!options.signal.aborted) {
		let answer: Answer<TraceView>;
		try {
			answer = await read<TraceView>(options.base, tracePath(options.runId, options.stepId, after), options.fetcher);
		} catch {
			await sleep(ASK_AGAIN_MS);
			continue;
		}
		if (options.signal.aborted) return;
		if (!answer.ok) {
			if (answer.problem.status === 401) options.onRefused();
			else options.onAbsent();
			return;
		}
		lines = merged(lines, answer.body.lines);
		after = answer.body.after;
		options.onTrace(answer.body, lines);
		if (!answer.body.open) return;
		await sleep(ASK_AGAIN_MS);
	}
}
