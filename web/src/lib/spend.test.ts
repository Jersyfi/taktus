// Where a process spends, per step, two runs side by side, and model trials (#449, #448;
// ADR-0148, ADR-0149). Each page is drawn from the surface's own answer — `fixtures.spend`,
// written by `make generate` with the types the routes answer with — opens with its sentence,
// charts one measure per axis from zero, says what could not be priced, and names no person.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ComparisonView from './ComparisonView.svelte';
import fixtures from './generated/fixtures.json';
import ProcessSpendView from './ProcessSpendView.svelte';
import SpendView from './SpendView.svelte';
import {
	comparisonSentence,
	kindsOf,
	money,
	moneyBars,
	mostMoney,
	processSentence,
	processSpendLink,
	rows,
	spendLink,
	spendSentence,
	stepLine,
	tokenBars,
	tokensIn,
	trialSentence,
	trialsLink,
	type ProcessSpend,
	type RunComparison,
	type RunSpend,
	type TrialRead,
	type Trials
} from './spend';
import TrialsView from './TrialsView.svelte';
import TrialView from './TrialView.svelte';

const run = fixtures.spend.run as unknown as RunSpend;
const comparison = fixtures.spend.comparison as unknown as RunComparison;
const process = fixtures.spend.process as unknown as ProcessSpend;
const trial = fixtures.spend.trial as unknown as TrialRead;
const trials = fixtures.spend.trials as unknown as Trials;

describe('the spend of a run', () => {
	it('splits a step by price kind and counts its tokens in as the surface does', () => {
		const draft = run.steps[1]!;
		expect(kindsOf(draft.meter)).toEqual({ input: 1200, cache_write: 400, cache_read: 8000, output: 310 });
		expect(tokensIn(draft.meter)).toBe(9600);
		expect(stepLine(draft, run.currency)).toBe(
			'draft: 0.0184 USD, 12.400 Takte, 1,200 plain input, 400 cache writes, 8,000 cache reads, 310 output, 3 turns, compression saved 2,400 of 12,000 input tokens.'
		);
	});

	it('draws money per step on one axis from zero, the step that spent most at full length', () => {
		const bars = moneyBars(run.steps, run.currency);
		expect(bars.map((b) => b.step)).toEqual(['read', 'draft', 'check']);
		expect(bars[1]!.share).toBe(1);
		expect(bars[0]!.share).toBe(0);
		expect(bars[2]!.share).toBeCloseTo(0.0021 / 0.0184);
		const tokens = tokenBars(run.steps);
		expect(tokens[1]!.parts.map((p) => p.kind)).toEqual(['input', 'cache_write', 'cache_read', 'output']);
		expect(tokens[1]!.parts.reduce((sum, p) => sum + p.share, 0)).toBeCloseTo(1);
	});

	it('says what could not be priced, never zero', () => {
		expect(money(null, 'usd')).toBe('not priced');
		expect(money(0.5, null)).toBe('not priced');
		const unpriced: RunSpend = { ...run, amount: null, steps: run.steps.map((s) => ({ ...s, amount: null })) };
		expect(spendSentence(unpriced)).toContain('nothing that could be priced');
		expect(moneyBars(unpriced.steps, null).every((b) => b.share === 0 && b.label === 'not priced')).toBe(true);
	});

	it('opens with its sentence, draws both charts, and links the run, the process and a comparison', () => {
		expect(spendSentence(run)).toBe('Run run_replies_1 spent 0.0205 USD over 3 steps, most of it in draft.');
		const { body } = render(SpendView, { props: { spend: run } });
		expect(body).toContain('Money per step');
		expect(body).toContain('Tokens per step, by price kind');
		expect(body).toContain('cache reads');
		expect(body).toContain('href="#/runs/run_replies_1"');
		expect(body).toContain(`href="${processSpendLink('replies')}"`);
		expect(body).toContain('15.00');
		expect(body).toContain('uncalibrated');
		expect(body).not.toMatch(/idn_/);
	});
});

describe('two runs side by side', () => {
	it('opens with what changed in money and which steps produced another result', () => {
		expect(comparisonSentence(comparison)).toBe(
			'Run run_replies_2 spent 0.0113 USD less, and draft produced a different result.'
		);
	});

	it('sets both runs on one axis and names each in the legend', () => {
		const most = mostMoney(comparison.left.steps, comparison.right.steps);
		const chart = rows(
			moneyBars(comparison.left.steps, 'usd', most),
			moneyBars(comparison.right.steps, 'usd', most)
		);
		expect(chart.find((r) => r.step === 'draft')!.bars.map((b) => b.share)).toEqual([1, 0.0071 / 0.0184]);
		const { body } = render(ComparisonView, { props: { compared: comparison } });
		expect(body).toContain('run_replies_1');
		expect(body).toContain('run_replies_2');
		expect(body).toContain('different result');
		expect(body).toContain('−0.0113 USD');
		expect(body).toContain(`href="${spendLink('run_replies_1')}"`);
	});
});

describe('the spend of a process', () => {
	it('opens with its money over the window and draws the steps', () => {
		expect(processSentence(process)).toBe('replies spent 0.2870 USD in 14 runs, most of it in draft.');
		const { body } = render(ProcessSpendView, { props: { spend: process, days: 30, onDays: () => {} } });
		expect(body).toContain('aria-pressed="true"');
		expect(body).toContain('finished 14 times');
	});
});

describe('model trials', () => {
	it('opens with the cases each candidate passed, and sets the results side by side', () => {
		expect(trialSentence(trial)).toBe(
			'2 models tried for drafting on 1 case: model.fast passed 1, model.careful passed 1 of 1.'
		);
		const { body } = render(TrialView, { props: { read: trial } });
		expect(body).toContain('Money per candidate');
		expect(body).toContain('Wall time per candidate');
		expect(body).toContain('results differ');
		expect(body).toContain('href="#/runs/trl_1-0-0"');
		expect(body).toContain('stays your act');
	});

	it('lists the offers, each startable, and every trial', () => {
		const { body } = render(TrialsView, { props: { trials, onStart: () => {} } });
		expect(body).toContain('A model changed its version');
		expect(body).toContain('Run the trial');
		expect(body).toContain(`href="${trialsLink('trl_1')}"`);
		expect(body).not.toMatch(/idn_/);
	});
});
