// What Today and the frame show, read in one request: `GET /levels/today` (ADR-0318, ADR-0322
// §4, ADR-0323 §4). The overview, the counts, at most five things that wait, and what the
// navigation marks. Every figure is one the surface counted; a count it withheld is null, and the
// page leaves its tile out instead of showing a zero. A read that failed is a failure, never an
// empty Today.

import { operationLines, operationSentence, type OperationSummary } from './operation';
import { readShared } from './shared';
import type { Line } from './governance';
import type { OverviewLevel, Problem } from './types';

/** How many waits the surface lists; the counts say how many there are in all. */
export const WAITS_ON_TODAY = 5;

/** `counts` as the surface answers it (ADR-0318 §1). */
export interface Counts {
	/** Decision requests addressed to the reader, open needs, open reports, alerts in effect. */
	waiting_for_you: number | null;
	/** Runs working right now, by the run component's definition. */
	running_now: number | null;
	/** Runs waiting on a person right now. */
	waiting_on_a_person: number | null;
	/** Runs that failed — escalated — in the last 24 hours. */
	failed_last_24h: number | null;
	open_incidents: number | null;
	/** Alerts in effect; null for a reader who does not read alerts. */
	open_alerts: number | null;
}

export type WaitKind = 'decision' | 'need' | 'report' | 'failure' | 'alert';

/** One thing that waits, as the surface lists it (ADR-0318 §2). */
export interface WaitItem {
	kind: WaitKind;
	title: string;
	/** The route in the web app, after `#`. */
	link: string;
	/** Since when, as an ISO time. */
	since: string;
	/** Past its date, or in effect now. */
	urgent: boolean;
}

/** `marks` as the surface answers it: what the navigation marks. */
export interface Marks {
	requests?: { waiting: number; overdue: number };
	needs?: { readable: boolean; open: number | null };
	autonomy?: { below: number; raises: number };
	findings?: { readable: false } | { readable: true; level: string; in_review: number };
	operation?: OperationSummary;
}

export interface TodayData {
	overview: OverviewLevel;
	counts: Counts;
	waits: WaitItem[];
	/** The destinations that wait for the reader, from the marks. */
	marks: string[];
	/** The marks as lines, for the section that says what governs the work. */
	lines: Line[];
	/** The operation's own sentence: that it runs as expected, or what needs a look (ADR-0121). */
	operation: string | null;
}

interface TodayAnswer {
	overview: OverviewLevel;
	counts?: Partial<Counts>;
	waits?: Partial<WaitItem>[];
	marks?: Marks;
}

/** What each kind of wait is called on the page. */
export const KIND_WORD: Record<WaitKind, string> = {
	decision: 'Decision',
	need: 'Need',
	report: 'Report',
	failure: 'Failure',
	alert: 'Alert'
};

const COUNTS: (keyof Counts)[] = ['waiting_for_you', 'running_now', 'waiting_on_a_person', 'failed_last_24h', 'open_incidents', 'open_alerts'];

function plural(n: number, one: string, many: string): string {
	return `${n} ${n === 1 ? one : many}`;
}

/** The marks as the lines of what governs the work, worded as the pages that own them word
 * them (ADR-0122). A kind the reader does not read has no line. */
export function linesOf(marks: Marks): Line[] {
	const lines: Line[] = [];
	if (marks.requests) {
		const { waiting, overdue } = marks.requests;
		lines.push({
			kind: 'requests',
			href: '#/requests',
			text: `Decision requests: ${waiting === 0 ? 'none waits for you' : `${plural(waiting, 'waits', 'wait')} for you`}${overdue ? `, ${overdue} past its date` : ''}.`,
			waiting: waiting > 0
		});
	}
	if (marks.needs?.readable && marks.needs.open !== null) {
		const open = marks.needs.open;
		lines.push({ kind: 'needs', href: '#/needs', text: `Needs: ${open === 0 ? 'none open' : `${plural(open, 'is', 'are')} open`}.`, waiting: open > 0 });
	}
	if (marks.autonomy) {
		const { below, raises } = marks.autonomy;
		const parts = [`${plural(below, 'process runs', 'processes run')} below the stated level`];
		if (raises) parts.push(`${plural(raises, 'raise waits', 'raises wait')} for a person`);
		lines.push({ kind: 'autonomy', href: '#/autonomy', text: `Levels and corrections: ${parts.join(', ')}.`, waiting: below + raises > 0 });
	}
	if (marks.findings?.readable) {
		const waiting = marks.findings.in_review;
		lines.push({
			kind: 'findings',
			href: '#/findings',
			text: `Findings: ${marks.findings.level === 'review' ? `${plural(waiting, 'waits', 'wait')} for a review` : `reviewed at the level ${marks.findings.level}`}.`,
			waiting: waiting > 0
		});
	}
	return lines;
}

/** The destinations the navigation marks: a line that waits, an operation kind that is red. */
export function destinationsOf(marks: Marks): string[] {
	const found = new Set(linesOf(marks).filter((l) => l.waiting).map((l) => l.kind as string));
	if (marks.operation && operationLines(marks.operation).some((l) => l.red)) found.add('operation');
	return [...found];
}

/** The answer of the surface, in the shapes the pages draw. */
export function fromSurface(body: TodayAnswer): TodayData {
	const counts = Object.fromEntries(
		COUNTS.map((k) => {
			const v = body.counts?.[k];
			return [k, typeof v === 'number' && Number.isFinite(v) ? v : null];
		})
	) as unknown as Counts;
	const waits = (body.waits ?? [])
		.filter((w): w is WaitItem => typeof w.title === 'string' && typeof w.link === 'string' && typeof w.kind === 'string')
		.map((w) => ({ kind: w.kind, title: w.title, link: w.link, since: w.since ?? '', urgent: Boolean(w.urgent) }));
	const marks = body.marks ?? {};
	return {
		overview: body.overview,
		counts,
		waits,
		marks: destinationsOf(marks),
		lines: linesOf(marks),
		operation: marks.operation ? operationSentence(marks.operation) : null
	};
}

export type TodayRead = { ok: true; today: TodayData } | { ok: false; problem: Problem };

/** Today, from the surface's one summary. Shared with the frame within its window. */
export async function readToday(base: URL, fetcher: typeof fetch = fetch): Promise<TodayRead> {
	const summary = await readShared<TodayAnswer>(base, 'levels/today', fetcher);
	if (!summary.ok) return { ok: false, problem: summary.problem };
	if (!summary.body || typeof summary.body !== 'object' || !summary.body.overview) {
		return { ok: false, problem: { status: 0, title: 'Not understood', detail: 'The surface answered Today without its overview.' } };
	}
	return { ok: true, today: fromSurface(summary.body) };
}
