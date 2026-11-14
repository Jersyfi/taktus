// The runs the reader may see, a page at a time (ADR-0321 §2, ADR-0319 §2): `GET /runs`,
// newest first, narrowed where the runs are stored — `state` (repeatable) and `process`. The
// surface answers `next` where more follow; it is passed back as `cursor`.

import { read, type Answer } from './api';

/** A run as `GET /runs` answers it: the run component's record, of which the list shows a few
 * fields. */
export interface RunRow {
	id: string;
	process_version: string;
	state: string;
	rehearsal?: boolean;
	created_at: string;
	updated_at?: string;
}

export interface RunPage {
	runs: RunRow[];
	/** Where the next page starts; absent on the last. */
	next?: string;
}

export interface RunQuery {
	states?: string[];
	process?: string;
	cursor?: string;
	limit?: number;
}

/** The states a reader can narrow to, as the run component names them. */
export const RUN_STATES = ['planned', 'admitted', 'running', 'waiting_human', 'halted', 'escalated', 'finished'] as const;

/** The process of a run, without its version. */
export function processOfRun(run: Pick<RunRow, 'process_version'>): string {
	const at = run.process_version.lastIndexOf('@');
	return at > 0 ? run.process_version.slice(0, at) : run.process_version;
}

/** The path of one page of runs. */
export function runsPath(query: RunQuery): string {
	const params = new URLSearchParams();
	params.set('limit', String(query.limit ?? 50));
	for (const state of query.states ?? []) params.append('state', state);
	if (query.process) params.set('process', query.process);
	if (query.cursor) params.set('cursor', query.cursor);
	return `runs?${params}`;
}

/** One page of runs. */
export async function readRuns(base: URL, query: RunQuery, fetcher: typeof fetch = fetch): Promise<Answer<RunPage>> {
	const answer = await read<{ runs?: RunRow[]; next?: string | null }>(base, runsPath(query), fetcher);
	if (!answer.ok) return answer;
	return { ok: true, body: { runs: answer.body.runs ?? [], ...(answer.body.next ? { next: answer.body.next } : {}) } };
}

/** When a run was created, as the reader's clock shows it. */
export function when(iso: string): string {
	const at = new Date(iso);
	if (Number.isNaN(at.getTime())) return iso;
	return at.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}
