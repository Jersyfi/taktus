// When the web app reads a level again (ADR-0063).
//
// A level is read from the surface, never assembled from the stream: the stream says that
// something changed, and the level is read again from the component that owns it (ADR-0055
// §4). Reads are coalesced: while one is under way, every further change asks for exactly one
// more, so that a burst of changes costs two reads, not one per change.

import { read } from './api';
import { follow } from './stream';

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

export interface FollowLevel<T> {
	base: URL;
	/** The level's path under the surface, as `levels/runs/<id>`. */
	path: string;
	/** The stream's scope, as its query: `{ run: <id> }`. */
	scope: Record<string, string>;
	key: string;
	signal: AbortSignal;
	onLevel: (level: T) => void;
	onAbsent: () => void;
	onRefused: () => void;
	onConnected?: (connected: boolean) => void;
	fetcher?: typeof fetch;
	sleep?: (ms: number) => Promise<void>;
}

/**
 * Follows a level live: the scope's stream, and the level read again on its snapshot and on
 * every change. A refused key ends both; a level the reader may not see is absent.
 */
export async function followLevel<T>(options: FollowLevel<T>): Promise<void> {
	const fetcher = options.fetcher ?? fetch;
	const controller = new AbortController();
	const stopBoth = () => controller.abort();
	options.signal.addEventListener('abort', stopBoth);
	let refused = false;
	const refuse = () => {
		if (!refused) {
			refused = true;
			options.onRefused();
		}
		controller.abort();
	};
	const rereader = new Rereader(async () => {
		const answer = await read<T>(options.base, options.path, options.key, fetcher);
		if (controller.signal.aborted) return;
		if (answer.ok) options.onLevel(answer.body);
		else if (answer.problem.status === 401) refuse();
		else if (answer.problem.status === 404) options.onAbsent();
	});
	const url = new URL('changes', options.base);
	for (const [name, value] of Object.entries(options.scope)) url.searchParams.set(name, value);
	const ended = await follow({
		url,
		key: options.key,
		signal: controller.signal,
		fetcher,
		...(options.sleep ? { sleep: options.sleep } : {}),
		...(options.onConnected ? { onConnected: options.onConnected } : {}),
		onEvent: () => void rereader.request()
	});
	if (ended.reason === 'refused' && ended.status === 401) refuse();
	options.signal.removeEventListener('abort', stopBoth);
}
