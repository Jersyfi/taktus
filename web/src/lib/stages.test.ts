import { describe, expect, it } from 'vitest';
import { ofRun, watchLevel } from './live';
import type { StreamEvent } from './stream';
import { runLink, stagesLink } from './links';
import type { StageView } from './types';

const VIEW: StageView = {
	run_id: 'r1',
	state: 'The run waits for a person.',
	stages: [
		{ name: 'collect', state: 'done', text: 'collect: done.' },
		{
			name: 'approve',
			state: 'current',
			waiting_for: 'controller',
			text: 'approve: current. Waiting for the role controller.'
		},
		{ name: 'book', state: 'ahead', text: 'book: ahead.' }
	],
	summary: '1 of 3 stages done. The run waits for a person. Waiting for the role controller.',
	link: '/levels/runs/r1'
};

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': status < 400 ? 'application/json' : 'application/problem+json' }
	});
}

describe('the stages of a run', () => {
	it('lead to the run level, and live address the run', () => {
		expect(stagesLink('r 1')).toBe('#/stages/r%201');
		expect(runLink(VIEW.run_id)).toBe('#/runs/r1');
	});

	it('are read from the stages route at once and again on every change of the run', async () => {
		const seen: StageView[] = [];
		const reads: string[] = [];
		const listeners: ((e: StreamEvent) => void)[] = [];
		const hub = { subscribe: (l: (e: StreamEvent) => void) => (listeners.push(l), () => {}) };
		const fetcher = (async (input: RequestInfo | URL) => {
			reads.push(new URL(String(input)).pathname);
			return json(VIEW);
		}) as typeof fetch;
		watchLevel<StageView>({
			base: new URL('https://h.test/'),
			path: 'levels/runs/r1/stages',
			concerns: ofRun('r1'),
			hub,
			signal: new AbortController().signal,
			onLevel: (found) => seen.push(found),
			onAbsent: () => {},
			onRefused: () => {},
			onFailed: () => {},
			fetcher
		});
		await new Promise((r) => setTimeout(r, 5));
		for (const l of listeners) l({ kind: 'change', change: { position: '2', run: 'r1', kind: 'step.finished', recorded_at: 't', state: { step: 'succeeded' } } });
		await new Promise((r) => setTimeout(r, 5));
		expect(reads).toEqual(['/levels/runs/r1/stages', '/levels/runs/r1/stages']);
		expect(seen[0]?.stages.map((s) => s.state)).toEqual(['done', 'current', 'ahead']);
	});
});
