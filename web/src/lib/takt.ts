// The Takt of the tenant (ADR-0323 §3): the last 60 minutes as one mark per minute, drawn from
// recorded changes only — the history the surface keeps (`GET /changes/recent?minutes=60`) and the
// changes the frame's stream delivered since. Nothing here is estimated; a minute without a
// recorded change is a minute with nothing.

import { read } from './api';
import type { Change } from './types';

export const SPAN_MINUTES = 60;
const MINUTE = 60_000;

export interface Minute {
	/** The minute's start, in milliseconds since the epoch. */
	start: number;
	/** How many changes were recorded in it. */
	count: number;
	/** How many of them were a failure. */
	failed: number;
}

/** Whether a change records a failure: a step that failed, or a run escalated after it. */
export function isFailure(change: Change): boolean {
	return change.kind === 'step.failed' || change.kind === 'run.escalated' || change.state?.step === 'failed';
}

/** The changes merged by position, each once, oldest first. */
export function merged(...lists: Change[][]): Change[] {
	const seen = new Map<string, Change>();
	for (const list of lists) for (const c of list) seen.set(c.position, c);
	return [...seen.values()].sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at));
}

/** The last `span` minutes up to `now`, oldest first, each with the changes recorded in it. A
 * change outside the window, or with a time that does not parse, is not drawn. */
export function minutes(changes: Change[], now: number, span = SPAN_MINUTES): Minute[] {
	const end = Math.floor(now / MINUTE) * MINUTE + MINUTE;
	const first = end - span * MINUTE;
	const found: Minute[] = Array.from({ length: span }, (_, i) => ({ start: first + i * MINUTE, count: 0, failed: 0 }));
	for (const change of changes) {
		const at = Date.parse(change.recorded_at);
		if (Number.isNaN(at) || at < first || at >= end) continue;
		const minute = found[Math.floor((at - first) / MINUTE)]!;
		minute.count += 1;
		if (isFailure(change)) minute.failed += 1;
	}
	return found;
}

/** The strip in words: its text equivalent. */
export function taktLine(drawn: Minute[], changes: Change[], now: number): string {
	const total = drawn.reduce((n, m) => n + m.count, 0);
	const failed = drawn.reduce((n, m) => n + m.failed, 0);
	if (total === 0) return `No change was recorded in the last ${drawn.length} minutes.`;
	const last = changes.at(-1);
	const ago = last ? Math.max(0, Math.round((now - Date.parse(last.recorded_at)) / MINUTE)) : null;
	const when = ago === null ? '' : ago === 0 ? ' The last one less than a minute ago.' : ` The last one ${ago} ${ago === 1 ? 'minute' : 'minutes'} ago.`;
	const failures = failed ? `, ${failed} of them ${failed === 1 ? 'a failure' : 'failures'}` : '';
	return `${total} ${total === 1 ? 'change' : 'changes'} recorded in the last ${drawn.length} minutes${failures}.${when}`;
}

/** What the surface kept of the last hour (ADR-0317 §4): the changes, oldest first, and whether
 * they are all of them — the surface reads at most its newest 500. Null where the read failed. */
export async function recentChanges(
	base: URL,
	fetcher: typeof fetch = fetch
): Promise<{ changes: Change[]; complete: boolean } | null> {
	const answer = await read<{ minutes: number; changes: Change[]; complete: boolean }>(base, `changes/recent?minutes=${SPAN_MINUTES}`, fetcher);
	if (!answer.ok || !Array.isArray(answer.body?.changes)) return null;
	return { changes: answer.body.changes, complete: answer.body.complete !== false };
}
