// When the web app reads a level again (ADR-0063, ADR-0323 §2).
//
// A level is read from the surface, never assembled from the stream: the stream says that
// something changed, and the level is read again from the component that owns it (ADR-0055
// §4). The level is read at once; the frame's one stream of the tenant says when to read it
// again. Reads are coalesced: while one is under way, every further change asks for exactly one
// more, so that a burst of changes costs two reads, not one per change.

import { read } from './api';
import type { StreamEvent } from './stream';
import type { Change, Problem } from './types';

/** Runs `read` once now, and once more after it whenever it was asked again meanwhile. */
export class Rereader {
	private reading: Promise<void> | null = null;
	private again = false;

	constructor(private readonly read: () => Promise<void>) {}

	request(): Promise<void> {
		if (this.reading !== null) {
			this.again = true;
			return this.reading;
		}
		this.reading = (async () => {
			do {
				this.again = false;
				await this.read();
			} while (this.again);
			this.reading = null;
		})();
		return this.reading;
	}
}

/** Whatever delivers the stream's events: the frame's stream of the tenant (ADR-0323 §2). */
export interface Hub {
	subscribe(listener: (event: StreamEvent) => void): () => void;
}

export interface WatchLevel<T> {
	base: URL;
	/** The level's path under the surface, as `levels/runs/<id>`. */
	path: string;
	/** Whether a change concerns this level, so that it is read again. */
	concerns: (change: Change) => boolean;
	hub: Hub;
	signal: AbortSignal;
	onLevel: (level: T) => void;
	onAbsent: () => void;
	onRefused: () => void;
	/** The surface failed or refused otherwise: a 5xx, a lost network, a 403. Never shown as
	 * empty, never as a read that goes on forever (ADR-0322 §5). */
	onFailed: (problem: Problem) => void;
	fetcher?: typeof fetch;
}

/**
 * Watches a level: read at once, without waiting for the stream (ADR-0323 §2), and read again,
 * coalesced, on a snapshot — the stream reconnected — and on every change that concerns it.
 * Returns the way to read again by hand, after a failure.
 */
export function watchLevel<T>(options: WatchLevel<T>): { again: () => Promise<void> } {
	const fetcher = options.fetcher ?? fetch;
	const rereader = new Rereader(async () => {
		const answer = await read<T>(options.base, options.path, fetcher);
		if (options.signal.aborted) return;
		if (answer.ok) options.onLevel(answer.body);
		else if (answer.problem.status === 401) options.onRefused();
		else if (answer.problem.status === 404) options.onAbsent();
		else options.onFailed(answer.problem);
	});
	void rereader.request();
	const stop = options.hub.subscribe((event) => {
		if (options.signal.aborted) return;
		if (event.kind === 'snapshot' || options.concerns(event.change)) void rereader.request();
	});
	options.signal.addEventListener('abort', stop);
	return { again: () => rereader.request() };
}

/** A change concerns a run's level when it is of that run. */
export function ofRun(runId: string): (change: Change) => boolean {
	return (change) => change.run === runId;
}

/** A change concerns a process's level when it names that process. A change that names no
 * process — a surface that does not send the field yet — may concern any process. */
export function ofProcess(processId: string): (change: Change) => boolean {
	return (change) =>
		change.process === undefined || change.process === processId || change.process.startsWith(`${processId}@`);
}
