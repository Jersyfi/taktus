// Changing a process in dialogue in the web app (UC-4.15, ADR-0091 §6): a proposal is shown as its
// difference, step by step, in words; only a rehearsed proposal offers commissioning; every
// earlier version offers a rollback, the active one none; the page computes nothing.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ChangeView from './ChangeView.svelte';
import fixtures from './generated/fixtures.json';
import type { Evaluated, EvaluatedSide, ProcessLevel, Proposal, RunLevel } from './types';

const LEVEL = fixtures.process_level as unknown as ProcessLevel;
const nothing = () => {};
const handlers = {
	onAsk: nothing,
	onRehearse: nothing,
	onCommission: nothing,
	onDiscard: nothing,
	onRollback: nothing
};

function proposal(state: Proposal['state']): Proposal {
	return {
		id: 'prp_1',
		process_id: LEVEL.process.id,
		base_version: LEVEL.process.version,
		version: '9',
		request: 'a person signs the draft',
		state,
		created_at: '2026-10-12T10:00:00Z',
		rehearsal_run: state === 'rehearsed' ? 'run_9' : undefined,
		difference: {
			steps: [
				{ id: 'sign', change: 'added', after: { id: 'sign', method: 'human', reason: 'a person signs' } },
				{
					id: 'draft',
					change: 'changed',
					fields: ['reason'],
					before: { id: 'draft', method: 'llm', reason: 'free text', exactness: 'free' },
					after: { id: 'draft', method: 'llm', reason: 'free text, signed', exactness: 'free' }
				}
			]
		}
	};
}

function rehearsal(state: string, summary: string): Record<string, RunLevel> {
	return {
		prp_1: {
			run: { id: 'run_9', process_version: 'daily@proposal-prp_1', state, rehearsal: true } as RunLevel['run'],
			steps: [
				{ id: 'draft', method: 'llm', state: 'succeeded' },
				{ id: 'publish', method: 'rule', state: state === 'finished' ? 'rehearsed' : 'failed' }
			] as RunLevel['steps'],
			summary
		}
	};
}

describe('a proposal offers a rehearsal and shows what it did (UC-1.10)', () => {
	it('offers the rehearsal of a proposal that has none, and says it acts on nothing outside', () => {
		const html = render(ChangeView, { props: { level: LEVEL, proposals: [proposal('proposed')], ...handlers } }).body;
		expect(html).toContain('>Rehearse<');
		expect(html).toContain('acts on nothing outside');
		expect(html).not.toContain('data-rehearsal=');
	});

	it('shows a finished rehearsal step by step, as a rehearsal, and then offers commissioning', () => {
		const html = render(ChangeView, {
			props: { level: LEVEL, proposals: [proposal('rehearsed')], rehearsals: rehearsal('finished', 'All steps are done.'), ...handlers }
		}).body;
		expect(html).toContain('data-rehearsal="run_9"');
		expect(html).toContain('nothing left the system');
		expect(html).toContain('All steps are done.');
		expect(html).toMatch(/data-step-state="rehearsed"/);
		expect(html).toContain('Commission version 9');
	});

	it('does not offer commissioning while the rehearsal has not finished, and says where it stopped', () => {
		const stopped = render(ChangeView, {
			props: {
				level: LEVEL,
				proposals: [proposal('rehearsed')],
				rehearsals: rehearsal('escalated', 'Stopped at publish: no recorded response for pull_request.open.'),
				...handlers
			}
		}).body;
		expect(stopped).toContain('no recorded response for pull_request.open');
		expect(stopped).not.toContain('Commission version 9');
		const unread = render(ChangeView, { props: { level: LEVEL, proposals: [proposal('rehearsed')], ...handlers } }).body;
		expect(unread).toContain('cannot be read yet');
		expect(unread).not.toContain('Commission version 9');
	});
});

describe('a change in dialogue', () => {
	it('shows a proposal as its difference, step by step, in words', () => {
		const html = render(ChangeView, { props: { level: LEVEL, proposals: [proposal('proposed')], ...handlers } }).body;
		expect(html).toContain('a person signs the draft');
		expect(html).toMatch(/data-change="added"/);
		expect(html).toContain('human — a person signs');
		expect(html).toContain('was: llm · free — free text');
		expect(html).toContain('Rehearse');
		expect(html).not.toContain('Commission version 9');
	});

	it('offers commissioning only once the proposal is rehearsed, and links the rehearsal', () => {
		const html = render(ChangeView, {
			props: { level: LEVEL, proposals: [proposal('rehearsed')], rehearsals: rehearsal('finished', 'Done.'), ...handlers }
		}).body;
		expect(html).toContain('Commission version 9');
		expect(html).toContain('#/runs/run_9');
	});

	it('offers a rollback for every version but the active one, and shows no closed proposal', () => {
		const html = render(ChangeView, {
			props: { level: LEVEL, proposals: [proposal('commissioned'), proposal('discarded')], ...handlers }
		}).body;
		const active = LEVEL.process.versions.find((v) => v.active)!.version;
		for (const v of LEVEL.process.versions) {
			expect(html.includes(`Roll back to ${v.version}`)).toBe(v.version !== active);
		}
		expect(html).not.toContain('data-proposal=');
		expect(html).toContain('Say what should change.');
	});
});

function evaluated(
	verdict: Evaluated['verdict'],
	state: Evaluated['state'] = 'scored',
	override: Evaluated['override'] = null
): Record<string, Evaluated> {
	const side = (score: number | null, run: string): EvaluatedSide => ({
		score,
		run_id: run,
		run_state: 'finished',
		seconds: 2,
		tokens: 40,
		models: { draft: 'model-a-2026-10' },
		left_out: null,
		scores: [{ step: 'draft', method: 'rule', score, how: 'rule' }]
	});
	return {
		prp_1: {
			id: 'evl_1',
			purpose: 'change',
			state,
			verdict: state === 'scored' ? verdict : null,
			tolerance: 0.05,
			sides: [
				{ side: 'active', version: 'daily@1', score: 0.9, cases: 2, unscored: 0 },
				{ side: 'proposed', version: 'daily@proposal-prp_1', score: 0.6, cases: 2, unscored: 0 }
			],
			override,
			started_at: '2026-10-23T09:00:00Z',
			scored_at: state === 'scored' ? '2026-10-23T09:05:00Z' : null,
			scorers: [{ step: 'draft', method: 'rule', exactness: 'exact', rule: 'overlap' }],
			cases: [
				{ case: 'late-refund', active: side(1, 'run_a1'), proposed: side(0.6, 'run_p1'), change: -0.4 },
				{ case: 'lost-parcel', active: side(0.8, 'run_a2'), proposed: side(0.6, 'run_p2'), change: -0.2 }
			]
		}
	};
}

const held = (state: Proposal['state']): Proposal => ({ ...proposal(state), evaluation: 'evl_1' });
const finishedRehearsal = () => rehearsal('finished', 'Done.');

describe('a proposal held to its evaluation cases (UC-4.18, ADR-0134 §9)', () => {
	it('shows each case with the active version and the proposal beside each other, and the verdict', () => {
		const html = render(ChangeView, {
			props: {
				level: LEVEL,
				proposals: [held('rehearsed')],
				rehearsals: finishedRehearsal(),
				evaluations: evaluated('regressed'),
				...handlers
			}
		}).body;
		expect(html).toContain('Held to 2 evaluation cases');
		expect(html).toMatch(/data-verdict="regressed"/);
		expect(html).toMatch(/data-case="late-refund"/);
		expect(html).toContain('0.90');
		expect(html).toContain('0.60');
		expect(html).toContain('−0.40');
		expect(html).toContain('overlap');
		expect(html).toContain('#/runs/run_p1');
	});

	it('offers commissioning once the verdict passed, and against a regression only with a reason', () => {
		const passed = render(ChangeView, {
			props: {
				level: LEVEL,
				proposals: [held('rehearsed')],
				rehearsals: finishedRehearsal(),
				evaluations: evaluated('passed'),
				...handlers
			}
		}).body;
		expect(passed).toContain('Commission version 9</button>');
		expect(passed).not.toContain('against the verdict');
		const regressed = render(ChangeView, {
			props: {
				level: LEVEL,
				proposals: [held('rehearsed')],
				rehearsals: finishedRehearsal(),
				evaluations: evaluated('regressed'),
				...handlers
			}
		}).body;
		expect(regressed).not.toContain('Commission version 9</button>');
		expect(regressed).toContain('Commission version 9 against the verdict');
		expect(regressed).toContain('give your reason');
	});

	it('does not offer commissioning while the cases are being run', () => {
		const html = render(ChangeView, {
			props: {
				level: LEVEL,
				proposals: [held('rehearsed')],
				rehearsals: finishedRehearsal(),
				evaluations: evaluated(null, 'running'),
				...handlers
			}
		}).body;
		expect(html).toContain('being run');
		expect(html).toContain('waits until every case is scored');
		expect(html).not.toContain('Commission version 9');
	});

	it('shows a version commissioned against the verdict with the reason, never who gave it', () => {
		const html = render(ChangeView, {
			props: {
				level: LEVEL,
				proposals: [held('commissioned')],
				evaluations: evaluated('regressed', 'scored', {
					reason: 'the shorter reply is what customers asked for',
					at: '2026-10-23T09:10:00Z'
				}),
				...handlers
			}
		}).body;
		expect(html).toContain('Commissioned against the verdict');
		expect(html).toContain('the shorter reply is what customers asked for');
		expect(html).toContain('0.90 → 0.60');
		expect(html).not.toContain('idn_');
	});
});
