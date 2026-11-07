// The reader's views, the value ledger, the reports for a role and why a step was done
// (ADR-0241 to ADR-0244). Each page draws the surface's answer as handed over: a figure's value
// with its unit or why it is withheld, its marks, the export one link away; the proposals, the
// bus-factor trend and dependencies, the backlog as expectations; a report's lines; a step's
// explanation. Nothing names a person (principle 14).

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ExplanationPanel from './ExplanationPanel.svelte';
import {
	backlogLine,
	edgeLine,
	EXPORT_CSV,
	EXPORT_JSON,
	figureLine,
	figureMarks,
	figureValue,
	surfaceHref,
	triggerLine,
	viewsSentence,
	type Definitions,
	type Figure,
	type Proposals,
	type Transformation,
	type ValueIndex,
	type Views
} from './figures';
import RoleReportsView from './RoleReportsView.svelte';
import type { RunLevel } from './types';
import ValueView from './ValueView.svelte';
import ViewsView from './ViewsView.svelte';

const saved: Figure = {
	id: 'value.time_saved_hours',
	component: 'value',
	definition: 'Hours a person would have spent by hand',
	unit: 'h',
	scope: 'process',
	subject: 'invoice',
	value: 12.3456,
	assumption: true,
	method: 'runs finished times the minutes by hand'
};
const withheld: Figure = {
	id: 'value.bus_factor.supplier',
	component: 'value',
	definition: 'Processes that break without the supplier',
	unit: 'processes',
	scope: 'supplier',
	subject: 'connector.mail',
	value: null,
	withheld: 'unknown: verdict none recorded',
	method: "the supplier's current removal verdict"
};
const simulated: Figure = { ...saved, id: 'value.cost_saved', unit: 'EUR', value: 400, assumption: false, simulation: true };

const views: Views = {
	views: [{ id: 'controlling', title: 'Controlling', group_by: 'process', figures: [saved, withheld, simulated] }]
};

describe('the views', () => {
	it('gives a figure its value and unit, or why it is withheld, and its marks', () => {
		expect(figureValue(saved)).toBe('12.35 h');
		expect(figureValue(withheld)).toBe('withheld: unknown: verdict none recorded');
		expect(figureMarks(saved)).toEqual(['assumption']);
		expect(figureMarks(simulated)).toEqual(['simulation']);
		expect(figureMarks(withheld)).toEqual([]);
		expect(figureLine(saved)).toBe('value.time_saved_hours of process invoice: 12.35 h (assumption).');
	});

	it('opens with its views, marks each figure and links the export', () => {
		expect(viewsSentence(views)).toBe('1 view for you, with 3 figures.');
		expect(viewsSentence({ views: [] })).toBe('No view is set up for your roles.');
		const { body } = render(ViewsView, { props: { views } });
		expect(body).toContain('Controlling');
		expect(body).toContain('data-mark="assumption"');
		expect(body).toContain('data-mark="simulation"');
		expect(body).toContain('withheld: unknown');
		expect(body).toContain(`href="${EXPORT_CSV}"`);
		expect(body).toContain(`href="${EXPORT_JSON}"`);
		expect(body).not.toMatch(/idn_/);
	});

	it('links a path of the surface from the web app', () => {
		expect(EXPORT_CSV).toBe('../figures.csv');
		expect(surfaceHref('processes/invoice/takeover')).toBe('../processes/invoice/takeover');
		expect(surfaceHref('/figures')).toBe('../figures');
	});
});

describe('the value ledger', () => {
	const proposals: Proposals = {
		proposals: [{ kind: 'raise_autonomy', process: 'invoice', text: 'Raise invoice to level 3.', addressed_to: 'owner' }]
	};
	const index: ValueIndex = {
		figures: [withheld],
		trend: [
			{ day: '2026-11-01', without_taktus: 2, suppliers_broke: 0 },
			{ day: '2026-11-02', without_taktus: 1, suppliers_broke: 1 }
		],
		graph: [
			{ process: 'invoice', on: 'taktus', kind: 'taktus' },
			{ process: 'invoice', on: 'accounting', kind: 'role' },
			{ process: 'invoice', on: 'connector.mail', kind: 'supplier' }
		]
	};
	const transformation: Transformation = {
		figures: [{ ...saved, id: 'value.maturity', scope: 'unit', subject: 'finance', unit: 'share', value: 0.5, assumption: false }],
		index: [],
		backlog: [{ kind: 'entered', id: 'b1', unit: 'finance', title: 'Dunning', hours_per_month: 6, basis: 'stated by the owner', expectation: true }]
	};

	it('says each dependency and backlog entry in words, the backlog as an expectation', () => {
		expect(index.graph.map(edgeLine)).toEqual([
			'invoice cannot run without Taktus.',
			'invoice needs the role accounting.',
			'invoice breaks without the supplier connector.mail.'
		]);
		expect(backlogLine(transformation.backlog[0]!)).toBe('Dunning in finance: 6 h a month expected, from stated by the owner.');
	});

	it('draws the proposals, the trend per day, the edges and the backlog', () => {
		const { body } = render(ValueView, { props: { proposals, index, transformation } });
		expect(body).toContain('1 proposal for your roles.');
		expect(body).toContain('Raise autonomy');
		expect(body).toContain('Raise invoice to level 3.');
		expect(body).toContain('2026-11-02');
		expect(body).toContain('data-edge="supplier"');
		expect(body).toContain('data-expectation');
		expect(body).toContain('finance');
		expect(body).not.toMatch(/idn_/);
	});

	it('says what the surface refused, part by part', () => {
		const { body } = render(ValueView, {
			props: { proposals, index: null, transformation: null, problems: { index: 'not for you', transformation: 'not for you either' } }
		});
		expect(body).toContain('Raise invoice to level 3.');
		expect(body).toContain('not for you');
		expect(body).toContain('not for you either');
	});
});

describe('the reports for a role', () => {
	const definitions: Definitions = {
		definitions: [
			{ id: 'weekly-controlling', reader_role: 'controlling', trigger: 'schedule', every: 'week', hour: 8, weekday: 0, channel: 'channel.chat' },
			{ id: 'on-ask', reader_role: 'controlling', trigger: 'request', channel: 'channel.chat' }
		]
	};

	it('says when each report comes', () => {
		expect(triggerLine(definitions.definitions[0]!)).toBe('every Monday at 08:00');
		expect(triggerLine(definitions.definitions[1]!)).toBe('on request');
		expect(triggerLine({ ...definitions.definitions[0]!, every: 'day', hour: 17 })).toBe('every day at 17:00');
	});

	it('offers to compose each now, and shows the lines of one composed', () => {
		const composed = {
			'weekly-controlling': { title: 'Controlling, this week', items: [], lines: ['Nothing needs you this week.'], quiet: true }
		};
		const { body } = render(RoleReportsView, { props: { definitions, composed, onCompose: () => {} } });
		expect(body).toContain('2 reports for your roles.');
		expect(body).toContain('Compose it now');
		expect(body).toContain('every Monday at 08:00');
		expect(body).toContain('Nothing needs you this week.');
	});
});

describe('why a step was done', () => {
	it('offers a "Why?" for every step of the run', () => {
		const level = {
			run: { id: 'run_1' },
			steps: [
				{ id: 'read', state: 'succeeded' },
				{ id: 'draft', state: 'running' }
			]
		} as unknown as RunLevel;
		const { body } = render(ExplanationPanel, { props: { level, base: new URL('http://x/'), onRefused: () => {} } });
		expect(body).toContain('data-why="read"');
		expect(body).toContain('data-why="draft"');
		expect(body.match(/Why\?/g)?.length).toBe(2);
	});
});
