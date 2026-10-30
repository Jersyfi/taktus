// A message to a running worker step from the run's page (ADR-0156 §7): a running worker step
// offers a field, the text is read back before it is sent, and the surface's refusal is said with
// its reason.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import SteeringPanel from './SteeringPanel.svelte';
import { messageSaid, readMessage, sendMessage, steerable } from './steering';
import type { RunLevel, StepElement } from './types';

const TAKEN = fixtures.takeover.level as unknown as RunLevel;

function running(build: Partial<StepElement> = {}): RunLevel {
	return {
		...TAKEN,
		run: { ...TAKEN.run, state: 'running' },
		steps: TAKEN.steps
			.filter((s) => s.id !== 'fix')
			.map((s) => (s.id === 'build' ? { ...s, state: 'running', ...build } : s))
	};
}

describe('a running worker step can be sent a message (ADR-0156 §7)', () => {
	it('offers the field on a running worker step only, and on none while a person holds one', () => {
		expect(steerable(running()).map((s) => s.id)).toContain('build');
		expect(steerable(running({ state: 'succeeded' })).map((s) => s.id)).not.toContain('build');
		expect(steerable(TAKEN)).toEqual([]);
		const html = render(SteeringPanel, { props: { level: running(), onSend: () => {} } }).body;
		expect(html).toContain('data-steer="build"');
	});

	it('reads the text back as it will be sent, and sends none that is empty or too long', () => {
		expect(readMessage('  use the mirror  ')).toBe('use the mirror');
		expect(readMessage('   ')).toBeNull();
		expect(readMessage('x'.repeat(8001))).toBeNull();
	});

	it('sends the text to the step’s address, and says the reason of a refusal', async () => {
		const seen: { url: string; body: unknown }[] = [];
		const fetcher = (async (url: URL, init?: RequestInit) => {
			seen.push({ url: String(url), body: init?.body ? JSON.parse(String(init.body)) : undefined });
			return new Response(JSON.stringify({ message: 'msg_1' }), { status: 202 });
		}) as unknown as typeof fetch;
		await sendMessage(new URL('https://taktus.test/p/'), 'run 1', 'build', 'go', fetcher);
		expect(seen).toEqual([{ url: 'https://taktus.test/p/runs/run%201/steps/build/messages', body: { text: 'go' } }]);
		expect(messageSaid(false, 'build', 'the worker worker.x declares no steering')).toBe(
			'Not sent: the worker worker.x declares no steering.'
		);
		expect(messageSaid(true, 'build', '')).toContain('next boundary');
	});
});
