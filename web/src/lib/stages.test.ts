import { describe, expect, it } from 'vitest';
import { followLevel } from './live';
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

	it('are read from the stages route on the snapshot and again on every change', async () => {
		const seen: StageView[] = [];
		const reads: string[] = [];
		const controller = new AbortController();
		const fetcher = (async (input: RequestInfo | URL) => {
			const url = new URL(String(input));
			if (url.pathname.endsWith('/changes')) {
				const text =
					'event: snapshot\ndata: {"position":"1","scope":{"kind":"run","id":"r1"}}\n\n' +
					'event: change\ndata: {"position":"2","run":"r1"}\n\n';
				return new Response(new TextEncoder().encode(text), { status: 200 });
			}
			reads.push(url.pathname);
			return json(VIEW);
		}) as typeof fetch;
		await followLevel<StageView>({
			base: new URL('https://h.test/'),
			path: 'levels/runs/r1/stages',
			scope: { run: 'r1' },
			signal: controller.signal,
			onLevel: (found) => seen.push(found),
			onAbsent: () => {},
			onRefused: () => {},
			fetcher,
			// The stream stays away a moment, so that the reads it asked for land, and then ends.
			sleep: () =>
				new Promise<void>((r) =>
					setTimeout(() => {
						controller.abort();
						r();
					}, 20)
				)
		});
		expect(reads.every((p) => p === '/levels/runs/r1/stages')).toBe(true);
		expect(seen.length).toBeGreaterThan(0);
		expect(seen[0]?.stages.map((s) => s.state)).toEqual(['done', 'current', 'ahead']);
	});
});
