// The reader's views and their figures, the value ledger, the reports for a role and why a step
// was done the way it was, as the surface answers them (ADR-0241 to ADR-0244): `GET /views`,
// `GET /value/proposals`, `GET /value/index`, `GET /value/transformation`,
// `GET /reports/definitions`, `GET /reports/definitions/{id}/now` and
// `GET /levels/runs/{run}/steps/{step}/explanation`. The pages draw what they are handed:
// nothing here computes a figure, and no figure names a person (principle 14).

/** A figure as its owner handed it in. A figure without a value says why it is withheld. */
export interface Figure {
	id: string;
	component: string;
	definition: string;
	unit: string;
	scope: 'tenant' | 'process' | 'stream' | 'unit' | 'role' | 'supplier';
	subject: string;
	since?: string | null;
	until?: string | null;
	value?: number | null;
	withheld?: string | null;
	assumption?: boolean;
	simulation?: boolean;
	method: string;
	basis?: Record<string, unknown>;
}

/** One view the reader holds, with the figures it shows them. */
export interface View {
	id: string;
	title: string;
	group_by: string;
	figures: Figure[];
}

/** `GET /views`. */
export interface Views {
	views: View[];
}

/** Where the export is read, relative to the web app: the surface is the directory above it. */
export const EXPORT_CSV = '../figures.csv';
export const EXPORT_JSON = '../figures';

/** A path of the surface, as a link from the web app (served one directory below it). */
export function surfaceHref(path: string): string {
	return `../${path.replace(/^\/+/, '')}`;
}

/** A figure's value with its unit, or why it is withheld. The number is the surface's, only
 * rounded for reading. */
export function figureValue(f: Figure): string {
	if (f.value === null || f.value === undefined) return `withheld: ${f.withheld ?? 'no value'}`;
	return `${f.value.toLocaleString('en', { maximumFractionDigits: 2 })} ${f.unit}`;
}

/** What a figure is marked as: an assumption, a simulation, or neither. */
export function figureMarks(f: Figure): string[] {
	return [...(f.assumption ? ['assumption'] : []), ...(f.simulation ? ['simulation'] : [])];
}

/** One figure in words. */
export function figureLine(f: Figure): string {
	const marks = figureMarks(f);
	const marked = marks.length ? ` (${marks.join(', ')})` : '';
	return `${f.id} of ${f.scope} ${f.subject}: ${figureValue(f)}${marked}.`;
}

/** The sentence the views open with. */
export function viewsSentence(v: Views): string {
	if (v.views.length === 0) return 'No view is set up for your roles.';
	const figures = v.views.reduce((sum, view) => sum + view.figures.length, 0);
	return `${v.views.length} ${v.views.length === 1 ? 'view' : 'views'} for you, with ${figures} ${figures === 1 ? 'figure' : 'figures'}.`;
}

// --- the value ledger -----------------------------------------------------------------------

export interface Proposal {
	kind: 'target' | 'deterioration' | 'raise_autonomy' | 'optimise' | 'switch_off' | 'observe';
	process?: string | null;
	figure?: string | null;
	text: string;
	basis?: Record<string, unknown>;
	addressed_to: string;
}

/** `GET /value/proposals`. */
export interface Proposals {
	proposals: Proposal[];
}

const KINDS: Record<Proposal['kind'], string> = {
	target: 'Target missed',
	deterioration: 'Deterioration',
	raise_autonomy: 'Raise autonomy',
	optimise: 'Optimise',
	switch_off: 'Switch off',
	observe: 'Observe'
};

export function proposalKind(kind: string): string {
	return KINDS[kind as Proposal['kind']] ?? kind;
}

export interface TrendDay {
	day: string;
	without_taktus: number;
	suppliers_broke: number;
}

export interface Edge {
	process: string;
	on: string;
	kind: 'taktus' | 'role' | 'supplier' | string;
}

/** `GET /value/index`. */
export interface ValueIndex {
	figures: Figure[];
	trend: TrendDay[];
	graph: Edge[];
}

/** One dependency in words. */
export function edgeLine(e: Edge): string {
	if (e.kind === 'taktus') return `${e.process} cannot run without Taktus.`;
	if (e.kind === 'role') return `${e.process} needs the role ${e.on}.`;
	if (e.kind === 'supplier') return `${e.process} breaks without the supplier ${e.on}.`;
	return `${e.process} depends on ${e.on} (${e.kind}).`;
}

export interface BacklogEntry {
	kind: 'proposal' | 'discovered' | 'entered' | string;
	id: string;
	unit?: string | null;
	title: string;
	hours_per_month?: number | null;
	basis: string;
	expectation: boolean;
}

/** `GET /value/transformation`. */
export interface Transformation {
	figures: Figure[];
	index: Figure[];
	backlog: BacklogEntry[];
}

/** One entry of the backlog in words: what it is expected to bring, never what it brought. */
export function backlogLine(b: BacklogEntry): string {
	const hours =
		b.hours_per_month === null || b.hours_per_month === undefined
			? 'no hours stated'
			: `${b.hours_per_month.toLocaleString('en', { maximumFractionDigits: 1 })} h a month expected`;
	const unit = b.unit ? ` in ${b.unit}` : '';
	return `${b.title}${unit}: ${hours}, from ${b.basis}.`;
}

// --- the reports for a role ------------------------------------------------------------------

export interface ReportDefinition {
	id: string;
	reader_role: string;
	trigger: 'request' | 'schedule';
	every?: 'day' | 'week' | null;
	hour?: number | null;
	weekday?: number | null;
	channel: string;
}

/** `GET /reports/definitions`. */
export interface Definitions {
	definitions: ReportDefinition[];
}

/** `GET /reports/definitions/{id}/now`. */
export interface ComposedReport {
	title: string;
	items: { kind: string; text: string; ref: string }[];
	lines: string[];
	quiet: boolean;
}

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** When a report comes, in words. */
export function triggerLine(d: ReportDefinition): string {
	if (d.trigger === 'request') return 'on request';
	const hour = d.hour === null || d.hour === undefined ? '' : ` at ${String(d.hour).padStart(2, '0')}:00`;
	if (d.every === 'week') return `every ${WEEKDAYS[d.weekday ?? 0]}${hour}`;
	return `every day${hour}`;
}

// --- why a step was done the way it was ----------------------------------------------------

/** `GET /levels/runs/{run}/steps/{step}/explanation`. */
export interface StepExplanation {
	depth: string;
	language: string;
	lines: string[];
}
