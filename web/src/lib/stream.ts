// The stream of changes, read as Server-Sent Events (ADR-0055).
//
// The browser's own `EventSource` cannot send a header, and the key is sent in no other place,
// so the stream is read with `fetch` and a streamed body. The reader keeps the position of the
// last event it received and reconnects with it as `Last-Event-ID`, after the wait the stream
// names: it receives every change after it, or a fresh snapshot (ADR-0055 §6).

import type { Change, Snapshot } from './types';

export interface ServerEvent {
	event: string;
	id?: string;
	data: string;
}

/** Splits a stream of text into events. A comment line — the heartbeat — yields nothing. */
export class EventParser {
	private buffer = '';
	private event = '';
	private id: string | undefined;
	private data: string[] = [];
	retry: number | undefined;

	feed(chunk: string): ServerEvent[] {
		this.buffer += chunk;
		const found: ServerEvent[] = [];
		let end: number;
		while ((end = this.buffer.search(/\r\n|\r|\n/)) >= 0) {
			const line = this.buffer.slice(0, end);
			const breakLength = this.buffer.startsWith('\r\n', end) ? 2 : 1;
			this.buffer = this.buffer.slice(end + breakLength);
			const dispatched = this.line(line);
			if (dispatched) found.push(dispatched);
		}
		return found;
	}

	private line(line: string): ServerEvent | null {
		if (line === '') {
			if (this.data.length === 0) {
				this.event = '';
				return null;
			}
			const dispatched: ServerEvent = {
				event: this.event || 'message',
				data: this.data.join('\n'),
				...(this.id === undefined ? {} : { id: this.id })
			};
			this.event = '';
			this.data = [];
			return dispatched;
		}
		if (line.startsWith(':')) return null;
		const colon = line.indexOf(':');
		const field = colon < 0 ? line : line.slice(0, colon);
		let value = colon < 0 ? '' : line.slice(colon + 1);
		if (value.startsWith(' ')) value = value.slice(1);
		if (field === 'event') this.event = value;
		else if (field === 'data') this.data.push(value);
		else if (field === 'id') this.id = value;
		else if (field === 'retry' && /^\d+$/.test(value)) this.retry = Number(value);
		return null;
	}
}

export type StreamEvent = { kind: 'snapshot'; snapshot: Snapshot } | { kind: 'change'; change: Change };

export type Ended = { reason: 'refused'; status: number } | { reason: 'stopped' };

export interface Follow {
	url: URL;
	key: string;
	onEvent: (event: StreamEvent) => void;
	/** Told whenever the connection opens (true) or is lost (false). */
	onConnected?: (connected: boolean) => void;
	signal: AbortSignal;
	fetcher?: typeof fetch;
	sleep?: (ms: number) => Promise<void>;
}

const RETRY_DEFAULT = 1000;
const RETRY_AT_MOST = 30000;

function delay(ms: number, signal: AbortSignal): Promise<void> {
	return new Promise((resolve) => {
		const timer = setTimeout(resolve, ms);
		signal.addEventListener('abort', () => {
			clearTimeout(timer);
			resolve();
		});
	});
}

/** Follows the stream until the signal aborts or the surface refuses the key. */
export async function follow(options: Follow): Promise<Ended> {
	const fetcher = options.fetcher ?? fetch;
	const sleep = options.sleep ?? ((ms: number) => delay(ms, options.signal));
	let position: string | undefined;
	let retry = RETRY_DEFAULT;
	let failures = 0;
	while (!options.signal.aborted) {
		const headers: Record<string, string> = {
			Authorization: `Bearer ${options.key}`,
			Accept: 'text/event-stream'
		};
		if (position !== undefined) headers['Last-Event-ID'] = position;
		try {
			const response = await fetcher(options.url, { headers, signal: options.signal });
			if (response.status === 401 || response.status === 403 || response.status === 404) {
				return { reason: 'refused', status: response.status };
			}
			if (response.ok && response.body) {
				options.onConnected?.(true);
				failures = 0;
				const parser = new EventParser();
				const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
				for (;;) {
					const { value, done } = await reader.read();
					if (done) break;
					for (const event of parser.feed(value)) {
						if (event.id !== undefined) position = event.id;
						const parsed = JSON.parse(event.data) as unknown;
						if (event.event === 'snapshot') {
							options.onEvent({ kind: 'snapshot', snapshot: parsed as Snapshot });
						} else if (event.event === 'change') {
							options.onEvent({ kind: 'change', change: parsed as Change });
						}
					}
					if (parser.retry !== undefined) retry = parser.retry;
				}
			}
		} catch {
			if (options.signal.aborted) break;
		}
		options.onConnected?.(false);
		failures += 1;
		// The stream's own wait first; longer while the surface stays away.
		await sleep(Math.min(retry * 2 ** Math.max(0, failures - 1), RETRY_AT_MOST));
	}
	return { reason: 'stopped' };
}
