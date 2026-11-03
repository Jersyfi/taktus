// Where a process spends, per step, two runs side by side, and model trials (#449, #448;
// ADR-0148, ADR-0149). The shapes the surface answers, where each page lives, the sentence
// each page opens with, and the bars its chart draws. Every figure is one the surface handed
// over: nothing here prices, weighs or counts what the surface did not. No figure names a
// person (principle 14).

/** The tokens of one model, by price kind. */
export interface PriceKinds {
	input?: number | null;
	output?: number | null;
	cache_read?: number | null;
	cache_write?: number | null;
}

/** What a step used, as the ledger recorded it. */
export interface Meter {
	tokens?: Record<string, PriceKinds>;
	compute_seconds?: Record<string, number>;
	steps?: Record<string, number>;
	turns?: number;
	compression?: { before: number; after: number } | null;
}

export interface StepSpend {
	step_id: string;
	method?: string | null;
	finished: number;
	meter: Meter;
	amount?: number | null;
	unpriced?: string[];
	takte?: number | null;
	outcome?: string | null;
	result?: string | null;
}

/** `GET /runs/{id}/spend`. */
export interface RunSpend {
	run_id: string;
	process_version?: string | null;
	currency?: string | null;
	table?: string | null;
	steps: StepSpend[];
	amount?: number | null;
	unpriced?: string[];
	takte?: number | null;
	calibration?: string | null;
}

export interface StepDifference {
	step_id: string;
	amount?: number | null;
	tokens_in?: number | null;
	tokens_out?: number | null;
	turns?: number | null;
	same_result?: boolean | null;
}

/** `GET /runs/{id}/spend?against=OTHER`. */
export interface RunComparison {
	left: RunSpend;
	right: RunSpend;
	steps: StepDifference[];
	amount?: number | null;
	comparable?: string[];
}

/** `GET /processes/{id}/spend`. */
export interface ProcessSpend {
	process_id: string;
	since?: string | null;
	until?: string | null;
	runs: number;
	steps: StepSpend[];
	amounts?: Record<string, number>;
	unpriced?: string[];
}

export interface CaseOutcome {
	case: string;
	run_id: string;
	state?: string | null;
	passed: boolean;
	amount?: number | null;
	tokens_in?: number;
	tokens_out?: number;
	wall_seconds?: number | null;
	results?: Record<string, string>;
}

export interface CandidateReport {
	model: string;
	cases?: CaseOutcome[];
	passed?: number;
	amount?: number | null;
	currency?: string | null;
	tokens_in?: number;
	tokens_out?: number;
	wall_seconds?: number;
	unpriced?: string[];
}

export interface Trial {
	id: string;
	purpose: string;
	candidates: string[];
	occasion: string;
	started_at: string;
	cases?: { key: string; process_version: string; case: string }[];
	runs?: Record<string, Record<string, string>>;
	left_out?: Record<string, string>;
}

/** `GET /trials/{id}`. */
export interface TrialRead {
	trial: Trial;
	report: { purpose: string; candidates?: CandidateReport[]; differing?: string[] };
	settled: boolean;
}

export interface Offer {
	purpose: string;
	occasion: string;
	model: string;
	candidates: string[];
	reason: string;
	since?: string | null;
}

/** `GET /trials`. */
export interface Trials {
	trials: Trial[];
	offers: Offer[];
}

// --- where each page lives ------------------------------------------------------------------

/** A run's spend, or two runs side by side. The control plane builds the same route
 * (`spend_in_channel.py`). */
export function spendLink(runId: string, against?: string | null): string {
	const run = `#/spend/runs/${encodeURIComponent(runId)}`;
	return against ? `${run}/${encodeURIComponent(against)}` : run;
}

/** A process's spend over a window. */
export function processSpendLink(processId: string): string {
	return `#/spend/processes/${encodeURIComponent(processId)}`;
}

/** The model trials, and one of them. */
export function trialsLink(trialId?: string): string {
	return trialId ? `#/trials/${encodeURIComponent(trialId)}` : '#/trials';
}

// --- the figures ---------------------------------------------------------------------------

export const KINDS = ['input', 'cache_write', 'cache_read', 'output'] as const;
export type Kind = (typeof KINDS)[number];

/** The words each price kind is shown under. */
export const KIND_NAMES: Record<Kind, string> = {
	input: 'plain input',
	cache_write: 'cache writes',
	cache_read: 'cache reads',
	output: 'output'
};

/** A step's tokens by price kind, over every model it used. */
export function kindsOf(meter: Meter): Record<Kind, number> {
	const summed: Record<Kind, number> = { input: 0, cache_write: 0, cache_read: 0, output: 0 };
	for (const kinds of Object.values(meter.tokens ?? {})) {
		for (const kind of KINDS) summed[kind] += kinds[kind] ?? 0;
	}
	return summed;
}

/** Every input-side token, whatever its price, as the surface counts it. */
export function tokensIn(meter: Meter): number {
	const kinds = kindsOf(meter);
	return kinds.input + kinds.cache_read + kinds.cache_write;
}

export function tokensOut(meter: Meter): number {
	return kindsOf(meter).output;
}

/** Money, with its currency; what the surface could not price says so, never "0". */
export function money(amount: number | null | undefined, currency: string | null | undefined): string {
	if (amount === null || amount === undefined || !currency) return 'not priced';
	return `${amount.toFixed(4)} ${currency.toUpperCase()}`;
}

export function signed(amount: number | null | undefined, currency: string | null | undefined): string {
	if (amount === null || amount === undefined || !currency) return 'not comparable';
	const sign = amount > 0 ? '+' : amount < 0 ? '−' : '±';
	return `${sign}${Math.abs(amount).toFixed(4)} ${currency.toUpperCase()}`;
}

export function count(n: number): string {
	return n.toLocaleString('en');
}

/** One bar of a chart: its length as a share of the longest, and its parts. */
export interface Bar {
	step: string;
	share: number;
	label: string;
	parts: { kind: Kind; share: number; tokens: number }[];
}

/** One row of a chart: a step, and a bar per series — one run, or two side by side. */
export interface Row {
	step: string;
	bars: { series: number; share: number; label: string; parts?: Bar['parts'] }[];
}

/** One row per step, a bar per series, from the bars of each series in the same order. Steps
 * one series lacks get no bar there. */
export function rows(...series: Bar[][]): Row[] {
	const order: string[] = [];
	for (const bars of series) for (const bar of bars) if (!order.includes(bar.step)) order.push(bar.step);
	return order.map((step) => ({
		step,
		bars: series.flatMap((bars, i) => {
			const bar = bars.find((b) => b.step === step);
			return bar ? [{ series: i, share: bar.share, label: bar.label, parts: bar.parts }] : [];
		})
	}));
}

/** The bars of money per step: each as a share of the step that spent most. A step that could
 * not be priced has no bar, and says so. */
export function moneyBars(
	steps: StepSpend[],
	currency: string | null | undefined,
	most: number = mostMoney(steps)
): Bar[] {
	return steps.map((s) => ({
		step: s.step_id,
		share: most > 0 && s.amount ? s.amount / most : 0,
		label: money(s.amount, currency),
		parts: []
	}));
}

/** The bars of tokens per step, each split by price kind: shares of the step with most. */
export function tokenBars(steps: StepSpend[], most: number = mostTokens(steps)): Bar[] {
	return steps.map((s) => {
		const kinds = kindsOf(s.meter);
		const total = allTokens(s);
		return {
			step: s.step_id,
			share: most > 0 ? total / most : 0,
			label: `${count(total)} tokens`,
			parts: KINDS.filter((k) => kinds[k] > 0).map((k) => ({
				kind: k,
				share: total > 0 ? kinds[k] / total : 0,
				tokens: kinds[k]
			}))
		};
	});
}

function allTokens(step: StepSpend): number {
	const kinds = kindsOf(step.meter);
	return KINDS.reduce((sum, k) => sum + kinds[k], 0);
}

/** The most money any of the steps spent: the end of a money chart's axis. Pass the steps of
 * both runs to set two side by side on one axis. */
export function mostMoney(...steps: StepSpend[][]): number {
	return Math.max(0, ...steps.flat().map((s) => s.amount ?? 0));
}

/** The most tokens any of the steps used: the end of a token chart's axis. */
export function mostTokens(...steps: StepSpend[][]): number {
	return Math.max(0, ...steps.flat().map(allTokens));
}

/** One step's figures in words. */
export function stepLine(step: StepSpend, currency: string | null | undefined): string {
	const kinds = kindsOf(step.meter);
	const parts = [
		`${step.step_id}: ${money(step.amount, currency)}`,
		step.takte === null || step.takte === undefined ? 'Takte not weighed' : `${step.takte.toFixed(3)} Takte`,
		...KINDS.filter((k) => kinds[k] > 0).map((k) => `${count(kinds[k])} ${KIND_NAMES[k]}`)
	];
	if (step.meter.turns) parts.push(`${step.meter.turns} turns`);
	const compression = step.meter.compression;
	if (compression) {
		parts.push(`compression saved ${count(compression.before - compression.after)} of ${count(compression.before)} input tokens`);
	}
	if (step.finished > 1) parts.push(`finished ${step.finished} times`);
	return parts.join(', ') + '.';
}

/** The step that spent most money, or most tokens where nothing was priced. */
export function heaviest(steps: StepSpend[]): StepSpend | null {
	if (steps.length === 0) return null;
	const priced = steps.some((s) => (s.amount ?? 0) > 0);
	const weight = (s: StepSpend) => (priced ? (s.amount ?? 0) : tokensIn(s.meter) + tokensOut(s.meter));
	return steps.reduce((best, s) => (weight(s) > weight(best) ? s : best));
}

/** The sentence a run's spend opens with. */
export function spendSentence(spend: RunSpend): string {
	const most = heaviest(spend.steps);
	const total = spend.amount === null || spend.amount === undefined ? 'nothing that could be priced' : money(spend.amount, spend.currency);
	const where = most ? `, most of it in ${most.step_id}` : '';
	return `Run ${spend.run_id} spent ${total} over ${spend.steps.length} steps${where}.`;
}

/** The sentence two runs side by side open with. */
export function comparisonSentence(compared: RunComparison): string {
	const differ = compared.steps.filter((s) => s.same_result === false).map((s) => s.step_id);
	const change =
		compared.amount === null || compared.amount === undefined
			? 'Their money cannot be compared'
			: compared.amount < 0
				? `Run ${compared.right.run_id} spent ${money(-compared.amount, compared.right.currency)} less`
				: compared.amount > 0
					? `Run ${compared.right.run_id} spent ${money(compared.amount, compared.right.currency)} more`
					: 'Both spent the same';
	const results = differ.length === 0 ? 'and every step produced the same result' : `and ${differ.join(', ')} produced a different result`;
	return `${change}, ${results}.`;
}

/** The sentence a process's spend opens with. */
export function processSentence(spend: ProcessSpend): string {
	const amounts = Object.entries(spend.amounts ?? {});
	const total = amounts.length === 0 ? 'nothing that could be priced' : amounts.map(([c, a]) => money(a, c)).join(' and ');
	const most = heaviest(spend.steps);
	const where = most ? `, most of it in ${most.step_id}` : '';
	return `${spend.process_id} spent ${total} in ${spend.runs} ${spend.runs === 1 ? 'run' : 'runs'}${where}.`;
}

/** The sentence a trial opens with. The report decides nothing: the choice stays a person's. */
export function trialSentence(read: TrialRead): string {
	const candidates = read.report.candidates ?? [];
	const cases = read.trial.cases?.length ?? 0;
	const passed = candidates.map((c) => `${c.model} passed ${c.passed ?? 0}`).join(', ');
	const state = read.settled ? '' : ' Some runs have not finished yet.';
	return `${candidates.length} ${candidates.length === 1 ? 'model' : 'models'} tried for ${read.trial.purpose} on ${cases} ${cases === 1 ? 'case' : 'cases'}: ${passed} of ${cases}.${state}`;
}

const OCCASIONS: Record<string, string> = {
	introduced: 'A model is introduced',
	proposed: 'Taktus proposes another model',
	changed: 'A model changed its version',
	asked: 'Asked for'
};

export function occasion(name: string): string {
	return OCCASIONS[name] ?? name;
}

/** One offer in words. */
export function offerLine(offer: Offer): string {
	return `${occasion(offer.occasion)} for ${offer.purpose}: ${offer.reason}. A trial would compare ${offer.candidates.join(', ')}.`;
}
