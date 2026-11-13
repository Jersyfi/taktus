// The instance's health and an update prepared as a plan (ADR-0295, ADR-0296, UC-10.2).

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import HealthView from './HealthView.svelte';
import type { Health } from './operation';

const HEALTH: Health = {
	release: '1.0.0',
	ready: false,
	reason: 'the database schema is behind this build',
	roles: ['api', 'runner'],
	leading: true,
	backup: 'failing',
	alerts_in_effect: 2,
	incidents_open: 1
};

function text(html: string): string {
	return html.replaceAll(/<!--[^>]*-->/g, '').replaceAll(/\s+/g, ' ').replaceAll('&#39;', "'");
}

describe('the health page', () => {
	const html = text(render(HealthView, { props: { health: HEALTH, onPrepare: () => {} } }).body);

	it('opens with the release and whether it is ready, and why not', () => {
		expect(html).toContain('Taktus 1.0.0 is not ready: the database schema is behind this build.');
		expect(html).toContain('api, runner, leading');
	});

	it("leads to the tenant's backup, alerts and incidents", () => {
		expect(html).toContain('href="#/backup">failing');
		expect(html).toContain('href="#/alerts">2 in effect');
		expect(html).toContain('href="#/incidents">1 open');
	});

	it('marks the health and the update, the acts of the inventory, and says the update applies nothing', () => {
		expect(html).toContain('data-act="instance.health"');
		expect(html).toContain('data-act="instance.update"');
		expect(html).toContain('commissioning applies nothing, and a person carries the steps out');
	});
});
