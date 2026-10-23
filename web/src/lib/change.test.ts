// Changing a process in dialogue in the web app (UC-4.15, ADR-0091 §6): a proposal is shown as its
// difference, step by step, in words; only a rehearsed proposal offers commissioning; every
// earlier version offers a rollback, the active one none; the page computes nothing.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ChangeView from './ChangeView.svelte';
import fixtures from './generated/fixtures.json';
import type { ProcessLevel, Proposal, RunLevel } from './types';

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
