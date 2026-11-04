// The one navigation list and its marks (ADR-0178): every page reachable from the frame, each
// route current on one destination, and a mark only where the surface's own line says something
// waits for the reader.

import { describe, expect, it } from 'vitest';
import type { Line } from './governance';
import { BANDS, currentDestination, DESTINATIONS, waitingDestinations } from './navigation';
import type { OperationLine } from './operation';
import { changesLine, nothingWaits } from './today';

/** The route id of every page, from the files SvelteKit routes. */
const IDS = Object.keys(import.meta.glob('../routes/**/+page.svelte')).map((file) => {
	const id = file.replace(/^\.\.\/routes/, '').replace(/\/\+page\.svelte$/, '');
	return id === '' ? '/' : id;
});
function routeIds(): string[] {
	return IDS;
}

describe('the navigation', () => {
	it('puts every destination in exactly one band, in the bands’ order', () => {
		const bands = BANDS.map((b) => b.id);
		for (const d of DESTINATIONS) expect(bands).toContain(d.band);
		const order = DESTINATIONS.map((d) => bands.indexOf(d.band));
		expect(order).toEqual([...order].sort((a, b) => a - b));
		expect(new Set(DESTINATIONS.map((d) => d.id)).size).toBe(DESTINATIONS.length);
	});

	it('makes every page of the web app current on one destination', () => {
		const ids = routeIds();
		expect(ids.length).toBeGreaterThan(20);
		const lost = ids.filter((id) => currentDestination(id) === null);
		expect(lost).toEqual([]);
	});

	it('leads each destination to a page that exists', () => {
		const ids = routeIds();
		for (const d of DESTINATIONS) {
			const route = d.href.slice(1);
			expect(ids.some((id) => id === route || (route !== '/' && id.startsWith(route))), d.href).toBe(true);
		}
	});

	it('takes the longest route that names a page', () => {
		expect(currentDestination('/')).toBe('today');
		expect(currentDestination('/runs/[id]')).toBe('today');
		expect(currentDestination('/requests/[[id]]')).toBe('requests');
		expect(currentDestination('/dependencies/remove/[adapter]')).toBe('dependencies');
		expect(currentDestination('/nowhere')).toBeNull();
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
		expect([...waitingDestinations(governs, operation)].sort()).toEqual(['requests', 'signals']);
		expect(waitingDestinations([], []).size).toBe(0);
	});
});

describe('Today', () => {
	it('says how many changes arrived since the page opened', () => {
		expect(changesLine(0)).toBe('No change has arrived since you opened this page.');
		expect(changesLine(1)).toBe('1 change has arrived since you opened this page.');
		expect(changesLine(7)).toBe('7 changes have arrived since you opened this page.');
	});

	it('says nothing waits only of the kinds the surface answered', () => {
		expect(nothingWaits(['requests', 'autonomy', 'tenants'])).toBe('No decision request or raise of a level waits for you.');
		expect(nothingWaits(['requests', 'needs', 'autonomy', 'findings'])).toBe(
			'No decision request, need, raise of a level or finding in review waits for you.'
		);
		expect(nothingWaits(['tenants'])).toBeNull();
	});
});
