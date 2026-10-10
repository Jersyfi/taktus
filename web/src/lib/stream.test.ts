import { describe, expect, it } from 'vitest';
import { EventParser, follow, type StreamEvent } from './stream';

function body(...chunks: string[]): ReadableStream<Uint8Array> {
	const encoder = new TextEncoder();
	return new ReadableStream({
		start(controller) {
			for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
			controller.close();
		}
	});
}

describe('the event parser', () => {
	it('reads events across chunks, with their type, position and data', () => {
		const parser = new EventParser();
		expect(parser.feed('retry: 1000\n\nevent: snap')).toEqual([]);
		expect(parser.feed('shot\nid: h1\ndata: {"a":')).toEqual([]);
		expect(parser.feed('1}\n\n: heartbeat\n\nevent: change\r\nid: h2\r\ndata: {}\r\n\r\n')).toEqual([
			{ event: 'snapshot', id: 'h1', data: '{"a":1}' },
			{ event: 'change', id: 'h2', data: '{}' }
		]);
		expect(parser.retry).toBe(1000);
	});

	it('yields nothing for a heartbeat', () => {
		expect(new EventParser().feed(': heartbeat\n\n: heartbeat\n\n')).toEqual([]);
	});
});

describe('following the stream', () => {
	it('sends the key in the header, resumes from the last position, and stops when refused', async () => {
		const calls: { url: string; headers: Record<string, string> }[] = [];
		const answers = [
			new Response(
				body(
					'retry: 5\n\n',
					'event: snapshot\nid: h1\ndata: {"position":"h1","scope":{"kind":"run","id":"r"},"runs":[]}\n\n',
					'event: change\nid: h2\ndata: {"position":"h2","run":"r","kind":"step.started","recorded_at":"t","state":{"step":"running"}}\n\n'
				),
				{ status: 200 }
			),
			new Response(null, { status: 401 })
		];
		const fetcher = (async (url: URL, init: RequestInit) => {
			calls.push({ url: String(url), headers: init.headers as Record<string, string> });
			return answers.shift()!;
		}) as unknown as typeof fetch;
		const events: StreamEvent[] = [];
		const waited: number[] = [];
		const ended = await follow({
			url: new URL('https://taktus.test/x/changes?run=r'),
			key: 'tk_reader',
			signal: new AbortController().signal,
			onEvent: (e) => events.push(e),
			fetcher,
			sleep: async (ms) => void waited.push(ms)
		});
		expect(ended).toEqual({ reason: 'refused', status: 401 });
		expect(events.map((e) => e.kind)).toEqual(['snapshot', 'change']);
		expect(calls[0]!.headers['Authorization']).toBe('Bearer tk_reader');
		expect(calls[0]!.headers['Last-Event-ID']).toBeUndefined();
		expect(calls[1]!.headers['Last-Event-ID']).toBe('h2');
		expect(calls.every((c) => !c.url.includes('tk_reader'))).toBe(true);
		expect(waited).toEqual([5]);
	});
});
