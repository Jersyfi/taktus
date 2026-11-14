// The one navigation list and its marks (ADR-0178, ADR-0321): every page reachable from the frame,
// each route current on one destination, five bands with their folds, the trail of links, and a
// mark only where the surface's own line says something waits for the reader.

import { describe, expect, it } from 'vitest';
import type { Line } from './governance';
import {
	BANDS,
	BOTTOM,
	currentBottom,
	currentDestination,
	DESTINATIONS,
	markOf,
	TABS,
	trail,
	waitingDestinations
} from './navigation';
import type { OperationLine } from './operation';
import { glance, waitsLine } from './today';

/** The route id of every page, from the files SvelteKit routes. */
const IDS = Object.keys(import.meta.glob('../routes/**/+page.svelte')).map((file) => {
	const id = file.replace(/^\.\.\/routes/, '').replace(/\/\+page\.svelte$/, '');
	return id === '' ? '/' : id;
});

/** Pages another area of the same concept branch builds: the conversation's `#/ask` (DEC-0239
 * item 6). The frame names it; its page lands beside this one. */
const BUILT_ELSEWHERE = new Set(['#/ask']);

describe('the navigation', () => {
	it('has five bands, and puts every destination in exactly one, in the bands’ order', () => {
		expect(BANDS.map((b) => b.label)).toEqual(['For you', 'Work', 'Steer', 'Depends on', 'Keep running']);
		const bands = BANDS.map((b) => b.id);
		for (const d of DESTINATIONS) expect(bands).toContain(d.band);
		const order = DESTINATIONS.map((d) => bands.indexOf(d.band));
		expect(order).toEqual([...order].sort((a, b) => a - b));
		expect(new Set(DESTINATIONS.map((d) => d.id)).size).toBe(DESTINATIONS.length);
	});

	it('shows at most fifteen first entries; the rest sit in a fold (ADR-0321 §1)', () => {
		const first = DESTINATIONS.filter((d) => !d.more);
		expect(first.length).toBeLessThanOrEqual(15);
		for (const band of BANDS) expect(first.some((d) => d.band === band.id), band.id).toBe(true);
	});

	it('carries a permanent entry to ask Taktus in For you', () => {
		const ask = DESTINATIONS.find((d) => d.id === 'ask');
		expect(ask).toMatchObject({ href: '#/ask', band: 'you' });
		expect(ask?.more).toBeFalsy();
	});

	it('makes every page of the web app current on one destination', () => {
		expect(IDS.length).toBeGreaterThan(20);
		const lost = IDS.filter((id) => currentDestination(id) === null);
		expect(lost).toEqual([]);
	});

	it('leads each destination, each tab and each item of the bottom bar to a page that exists', () => {
		const hrefs = [...DESTINATIONS.map((d) => d.href), ...Object.values(TABS).flat().map((t) => t.href), ...BOTTOM.map((b) => b.href)];
		for (const href of hrefs) {
			if (BUILT_ELSEWHERE.has(href)) continue;
			const route = href.slice(1);
			expect(IDS.some((id) => id === route || (route !== '/' && id.startsWith(route))), href).toBe(true);
		}
	});

	it('makes a process, a run and an origin current on their lists, no longer on Today', () => {
		expect(currentDestination('/')).toBe('today');
		expect(currentDestination('/waits')).toBe('today');
		expect(currentDestination('/runs/[id]')).toBe('runs');
		expect(currentDestination('/runs')).toBe('runs');
		expect(currentDestination('/origins/[run]/[step]')).toBe('runs');
		expect(currentDestination('/processes/[id]/[[version]]')).toBe('processes');
		expect(currentDestination('/spend/processes/[id]')).toBe('processes');
		expect(currentDestination('/spend/runs/[id]/[[against]]')).toBe('runs');
		expect(currentDestination('/requests/[[id]]')).toBe('requests');
		expect(currentDestination('/dependencies/remove/[adapter]')).toBe('dependencies');
		expect(currentDestination('/nowhere')).toBeNull();
	});

	it('puts the pages of one question under one destination with tabs', () => {
		expect(['/catalogue', '/gallery', '/plans'].map(currentDestination)).toEqual(['start', 'start', 'start']);
		expect(['/value', '/views', '/role-reports'].map(currentDestination)).toEqual(['value', 'value', 'value']);
		expect(['/incidents', '/alerts', '/backup', '/signals', '/health'].map(currentDestination)).toEqual([
			'operation',
			'operation',
			'operation',
			'operation',
			'operation'
		]);
		for (const [id, tabs] of Object.entries(TABS)) {
			for (const t of tabs) expect(currentDestination(t.route), t.route).toBe(id);
		}
	});

	it('holds Today, Waits and Runs in the bottom bar of a phone', () => {
		expect(BOTTOM.map((b) => b.label)).toEqual(['Today', 'Waits', 'Runs']);
		expect(currentBottom('/runs/[id]')).toBe('runs');
		expect(currentBottom('/waits')).toBe('waits');
		expect(currentBottom('/needs')).toBeNull();
	});

	it('leads back along a trail of links, every step but the last one', () => {
		expect(trail('/runs/[id]', { id: 'r1' })).toEqual([{ label: 'Runs', href: '#/runs' }, { label: 'Run r1' }]);
		const origin = trail('/origins/[run]/[step]', { run: 'r 1', step: 'draft' });
		expect(origin.map((s) => s.href)).toEqual(['#/runs', '#/runs/r%201', undefined]);
		expect(trail('/processes/[id]/[[version]]', { id: 'invoices' })[0]).toEqual({ label: 'Processes', href: '#/processes' });
		expect(trail('/', {})).toEqual([]);
	});

	it('marks only what a line says waits, and nothing the surface refused', () => {
		const governs: Line[] = [
			{ kind: 'requests', href: '#/requests', text: 'Decision requests: 2 wait for you.', waiting: true },
			{ kind: 'needs', href: '#/needs', text: 'Needs: none open.', waiting: false }
		];
		const operation: OperationLine[] = [
			{ kind: 'incidents', label: 'Incidents', text: '0 incidents open of 0.', href: '#/incidents', red: false },
			{ kind: 'signals', label: 'Signals', text: '1 red, 0 yellow, 0 not measured, of 1.', href: '#/signals', red: true }
		];
		expect([...waitingDestinations(governs, operation)].sort()).toEqual(['operation', 'requests']);
		expect(waitingDestinations([], []).size).toBe(0);
		expect(markOf('alerts')).toBe('operation');
		expect(markOf('requests')).toBe('requests');
	});
});

describe('Today', () => {
	it('says what waits in the pulse card’s first tile, and never a count it did not read', () => {
		expect(waitsLine(0)).toBe('nothing waits for you');
		expect(waitsLine(1)).toBe('waits for you');
		expect(waitsLine(null)).toBe('waits could not be read');
	});

	it('leaves out a tile the surface did not count, instead of showing a zero', () => {
		const tiles = glance({ waiting_for_you: 2, running: 3, waiting_on_person: null, failed_24h: null, incidents: 0, alerts: 1 });
		expect(tiles.map((t) => t.key)).toEqual(['running', 'incidents', 'alerts']);
		expect(tiles.find((t) => t.key === 'alerts')?.alert).toBe(true);
		expect(tiles.find((t) => t.key === 'incidents')?.alert).toBe(false);
	});
});
