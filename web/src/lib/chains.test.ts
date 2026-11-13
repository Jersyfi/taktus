// A chain run's standing and a chain's objectives, as the chains page says them (ADR-0301 §4).

import { describe, expect, it } from 'vitest';
import { decisionPath, objectives, standing, type ChainRunView, type ChainView } from './chains';

const CHAIN: ChainView = {
	id: 'procure-to-pay',
	name: 'Procure to pay',
	links: [
		{ process_version: 'purchase-order@1' },
		{
			process_version: 'book-invoice@1',
			handover: [{ input: 'amount', step: 'order', clause: 'the booked amount is the ordered one' }]
		}
	],
	slo: { latency: 'PT1H', completion: 0.9 },
	declared_at: '2026-11-13T10:00:00Z',
	runs: []
};

function run(update: Partial<ChainRunView>): ChainRunView {
	return {
		id: 'chr_procure-to-pay_1',
		state: 'running',
		started_at: '2026-11-13T10:00:00Z',
		updated_at: '2026-11-13T10:00:00Z',
		link: 0,
		runs: ['run_1'],
		handovers: [],
		missing: [],
		...update
	};
}

describe('a chain on its page', () => {
	it('says where a run stands and what a halted handover lacks', () => {
		expect(standing(CHAIN, run({ state: 'halted', missing: ['amount'] }))).toBe(
			'Halted after purchase-order@1: the handover lacks amount.'
		);
		expect(standing(CHAIN, run({ state: 'waiting', link: 1 }))).toContain('goes on by itself');
		expect(standing(CHAIN, run({ state: 'finished', handovers: ['sha256:a'] }))).toBe(
			'Finished: every link ran, 1 handover(s) recorded.'
		);
	});

	it('says the chain’s own objectives, and nothing where it names none', () => {
		expect(objectives(CHAIN)).toBe('a run within PT1H, 90 % of runs finish');
		expect(objectives({ ...CHAIN, slo: undefined })).toBe('');
	});

	it('posts a decision to the chain run’s own path', () => {
		expect(decisionPath('chr_procure-to-pay_1')).toBe('chain-runs/chr_procure-to-pay_1/decision');
	});
});
