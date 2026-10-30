// What a person may ask Taktus for, and the organisation seen as value streams, in the web app
// (UC-1.13, UC-15.6, ADR-0159). Each page draws the surface's own answer — `make generate`
// writes it into the fixtures with the reporting component's functions — and nothing else.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import CatalogueView from './CatalogueView.svelte';
import fixtures from './generated/fixtures.json';
import StreamLanesView from './StreamLanesView.svelte';
import StreamsView from './StreamsView.svelte';
import {
	fallbacks,
	grid,
	inputsOf,
	METHOD_ORDER,
	segments,
	startEntry,
	streamLink,
	type Catalogue,
	type StreamLanes,
	type StreamMap
} from './views';

const CATALOGUE = fixtures.views.catalogue as unknown as Catalogue;
const STREAMS = fixtures.views.streams as unknown as StreamMap;
const LANES = fixtures.views.lanes as unknown as StreamLanes;

function unescape(text: string): string {
	return text.replaceAll('&amp;', '&').replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&lt;', '<').replaceAll('&gt;', '>');
}

describe('the catalogue', () => {
	it('lists each entry with what it needs, how to start it elsewhere, and the one command', () => {
		const html = unescape(render(CatalogueView, { props: { catalogue: CATALOGUE, onStart: () => {} } }).body);
		expect(html).toContain(CATALOGUE.summary);
		for (const entry of CATALOGUE.entries) {
			expect(html).toContain(entry.text);
			expect(html).toContain(entry.command.intent);
			expect(html).toContain(`Start ${entry.name}`);
		}
		expect(html).toMatch(/write <code[^>]*>start daily<\/code>/);
		expect(html).toContain('name="client"');
		expect(html).toContain(CATALOGUE.nothing_fits);
	});

	it('is a list and a start button: no ticket, no queue, no promised time', () => {
		const html = unescape(render(CatalogueView, { props: { catalogue: CATALOGUE, onStart: () => {} } }).body).toLowerCase();
		for (const word of ['ticket', 'queue', 'sla', 'due date', 'priority']) expect(html).not.toContain(word);
	});

	it('starts an entry as the reader, with the inputs as written and an empty optional one left out', async () => {
		const offer = CATALOGUE.entries.find((e) => e.process === 'offer')!;
		expect(inputsOf(offer, { client: ' Acme ' })).toEqual({ client: 'Acme' });
		const calls: { url: string; init?: RequestInit }[] = [];
		const fetcher = (async (url: URL, init?: RequestInit) => {
			calls.push({ url: String(url), init });
			return new Response(JSON.stringify({ run_id: 'run_1', process_version: 'offer@1', state: 'planned' }), {
				status: 201
			});
		}) as unknown as typeof fetch;
		const answer = await startEntry(new URL('https://instance.test/p/'), 'offer', { client: 'Acme' }, fetcher);
		expect(answer.ok && answer.body.run_id).toBe('run_1');
		expect(calls[0]!.url).toBe('https://instance.test/p/catalogue/offer/start');
		expect(calls[0]!.init?.method).toBe('POST');
		expect(calls[0]!.init?.body).toBe('{"inputs":{"client":"Acme"}}');
	});
});

describe('the value streams', () => {
	it('draws three tiers, each card opening its swimlanes, and the processes in no stream', () => {
		const html = unescape(render(StreamsView, { props: { view: STREAMS } }).body);
		expect(html).toContain(STREAMS.summary);
		const [core] = STREAMS.core;
		expect(html).toContain(`href="${streamLink(core!.stream)}"`);
		expect(html).toContain(core!.trigger);
		expect(html).toContain(core!.outcome);
		expect(html).toContain(core!.text);
		expect(html.indexOf('data-stream="planning"')).toBeLessThan(html.indexOf('data-stream="order-to-cash"'));
		expect(html).toContain('In no stream');
		expect(html).toContain('No figure names a person.');
	});

	it('orders a method mix reproducible first, and leaves out what is not there', () => {
		expect(segments({ human: 0.4, llm: 0.2, rule: 0.4 }, METHOD_ORDER).map((s) => s.key)).toEqual([
			'rule',
			'llm',
			'human'
		]);
	});

	it('opens a stream as lanes by columns, with each chip in its lane and a fallback in its role', () => {
		const rows = grid(LANES);
		expect(rows.map((r) => r.lane.key)).toEqual(['taktus.reproducible', 'taktus.variable', 'role:sales', 'role:accounting']);
		const variable = rows[1]!;
		expect(variable.cells[0]!.map((c) => c.step)).toEqual(['read']);
		expect(fallbacks(LANES, rows[2]!.lane, 'order').map((c) => c.step)).toEqual(['read']);
		const html = unescape(render(StreamLanesView, { props: { view: LANES } }).body);
		for (const column of LANES.columns) expect(html).toContain(column.name);
		for (const lane of LANES.lanes) expect(html).toContain(lane.text);
		expect(html).toContain('data-fallback="order/read"');
		expect(html).toContain('Show departments');
		expect(html).toContain('too few hold it to show its waiting');
	});
});
