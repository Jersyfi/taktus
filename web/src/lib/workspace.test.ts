// The plan dialogue, the coach, the structure and the administration in the web app
// (ADR-0279): the guided start asks what to automate and explains its terms, the expert mode
// shows every field, every setting is shown with its value and why; the coach shows the
// reader's own hints and states its default; the structure draws its tree in the organisation's
// levels; every administrative act is a form marked with its name.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import AdministrationView from './AdministrationView.svelte';
import CoachView from './CoachView.svelte';
import PlanView from './PlanView.svelte';
import StructureView from './StructureView.svelte';
import type { PlanDraftView, Structure } from './workspace';
import { answerValue, tree } from './workspace';

const nothing = () => {};
const plan = { onOpen: nothing, onPick: nothing, onAnswer: nothing, onSet: nothing, onMode: nothing, onCommission: nothing };

const DRAFT: PlanDraftView = {
	draft: { id: 'pld_1', version: 2, goal: 'send the weekly report' },
	mode: 'guided',
	plan_version: 'pld_1@v2',
	commissioned: false,
	missing: ['the date it is due'],
	unestimable: [],
	estimates: [],
	settings: [
		{ field: 'goal', value: 'send the weekly report', why: 'what the plan is for, in your words', asked: true },
		{ field: 'results_in', value: 'run', why: 'a plan runs once', asked: false }
	],
	question: {
		field: 'autonomy_level',
		asks: 'Should you confirm every step before Taktus acts (level 2)?',
		explains: 'The autonomy level is how much Taktus does on its own.',
		step_id: null
	}
};

describe('the guided start and the plan dialogue (UC-10.3, UC-1.2, UC-13.1)', () => {
	it('starts by asking what to automate, in plain words', () => {
		const html = render(PlanView, { props: { ...plan } }).body;
		expect(html).toContain('What would you like to automate?');
		expect(html).toContain('data-start');
		expect(html).toContain('Nothing runs until you say so.');
	});

	it('asks one question, explains its term, and shows every setting with its value and why', () => {
		const html = render(PlanView, { props: { ...plan, view: DRAFT } }).body;
		expect(html).toContain('data-question="autonomy_level"');
		expect(html).toContain('The autonomy level is how much Taktus does on its own.');
		expect(html).toContain('What the plan ends in (not asked)');
		expect(html).toContain('run — a plan runs once');
		expect(html).toContain('Commissioning means you say: run it as planned.');
		expect(html).toContain('Still missing: the date it is due.');
	});

	it('shows every field at once in the expert mode and asks nothing', () => {
		const html = render(PlanView, { props: { ...plan, view: { ...DRAFT, mode: 'expert', question: null } } }).body;
		expect(html).toContain('data-expert');
		expect(html).not.toContain('data-question');
		expect(html).toContain('Autonomy level (1 to 4)');
	});

	it('turns a typed answer into the field the question asks for', () => {
		const q = DRAFT.question!;
		expect(answerValue(q, '2')).toBe(2);
		expect(answerValue({ ...q, field: 'estimates' }, '30 the last runs')).toEqual({ figure: 30, unit: 'seconds', basis: 'the last runs' });
		expect(answerValue({ ...q, field: 'steps' }, 'invoices@3')).toEqual({ process_version: 'invoices@3' });
	});
});

describe('the coach (UC-13.3)', () => {
	const coach = {
		settings: { on: true, hints_per_week: 1, default_hints_per_week: 1 },
		hints: [{ id: 'h1', says: 'You ask "summarise" every Monday.', procedure: 'every Monday', offered_at: '2026-11-07' }],
		share: { lasted: 1, checked: 2 }
	};
	const handlers = { onSet: nothing, onDismiss: nothing, onAccept: nothing };

	it('shows the reader their hint, the default where it is set, and their own share', () => {
		const html = render(CoachView, { props: { coach, ...handlers } }).body;
		expect(html).toContain('You ask "summarise" every Monday.');
		expect(html).toContain('Hints a week (default 1)');
		expect(html).toContain('1 of 2 still run');
	});

	it('says that a coach switched off reads nothing', () => {
		const off = { ...coach, settings: { ...coach.settings, on: false } };
		const html = render(CoachView, { props: { coach: off, ...handlers } }).body;
		expect(html).toContain('data-off');
		expect(html).not.toContain('data-hint');
	});
});

describe('the structure (UC-1.4, UC-1.6)', () => {
	const structure: Structure = {
		levels: ['company', 'area', 'team', 'project'],
		units: [
			{ id: 'acme', name: 'Acme', level: 0 },
			{ id: 'ops', name: 'Operations', level: 1, parent: 'acme' },
			{ id: 'web', name: 'Web', level: 2, parent: 'ops' }
		],
		placements: [{ kind: 'process', object: 'invoices', unit: 'web' }],
		yours: ['web']
	};

	it('orders the units as a tree and names their levels as the organisation does', () => {
		expect(tree(structure.units).map((t) => [t.unit.id, t.depth])).toEqual([
			['acme', 0],
			['ops', 1],
			['web', 2]
		]);
		const html = render(StructureView, {
			props: {
				structure,
				onAddUnit: nothing,
				onPlace: nothing,
				onLevels: nothing,
				onKnowledge: nothing,
				onWhere: nothing,
				onCreateProject: nothing,
				onOpenSession: nothing,
				onSay: nothing,
				onPlan: nothing
			}
		}).body;
		expect(html).toContain('team · yours');
		expect(html).toContain('process: invoices');
		for (const act of ['structure.levels', 'structure.unit', 'structure.place', 'structure.knowledge', 'structure.where', 'project.create'])
			expect(html).toContain(`data-act="${act}"`);
	});
});

describe('the administration (UC-10.2)', () => {
	it('offers every act of the tenant as a form marked with its name', () => {
		const html = render(AdministrationView, {
			props: { links: [{ id: 'lnk_1', channel: 'channel.chat', identity: 'idn_ada' }], onAct: nothing }
		}).body;
		for (const act of [
			'identity.add',
			'identity.key',
			'identity.agent-key',
			'identity.roles',
			'identity.grant',
			'identity.withdraw',
			'identity.rights',
			'identity.links',
			'identity.revoke',
			'units.set',
			'units.clear',
			'units.show'
		])
			expect(html).toContain(`data-act="${act}"`);
	});
});
