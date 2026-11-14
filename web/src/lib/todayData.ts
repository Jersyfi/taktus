// What Today shows, read in one place (ADR-0322 §4, ADR-0323 §4). The surface's one summary,
// `GET /levels/today`, is read first. Where it is not served, the same is put together from the
// reads that existed before it: the overview, `GET /operation`, the decision requests addressed to
// the reader and the reports to the owner — shared with the frame, so none is read twice. Every
// figure is one the surface counted; a figure no read counted is null, and the page leaves its
// tile out instead of showing a zero.

import type { Answer } from './api';
import { requestsLink, reportLink } from './links';
import { waitingDestinations } from './navigation';
import { operationLines, operationSentence, type OperationSummary } from './operation';
import { openReports, type ReportList } from './reports';
import { readShared } from './shared';
import type { AddressedRequest, OverviewLevel, Problem } from './types';
import { governanceLines, type Line } from './governance';

/** What each kind of wait is called on the page. */
export const KIND_WORD: Record<string, string> = {
	decision: 'Decision',
	need: 'Need',
	date: 'Date',
	failure: 'Failure',
	signals: 'Daily signals',
	raise: 'Levels',
	finding: 'Findings'
};

/** How many waits Today lists; the rest are on `#/waits`. */
export const WAITS_ON_TODAY = 5;

export interface Counts {
	/** Items that wait for the reader: decision requests addressed to them, open reports. */
	waiting_for_you: number | null;
	/** Runs working right now, by the run component's definition. */
	running: number | null;
	/** Runs waiting on a person right now. */
	waiting_on_person: number | null;
	/** Runs that failed in the last 24 hours. */
	failed_24h: number | null;
	/** Incidents open. */
	incidents: number | null;
	/** Alerts in effect. */
	alerts: number | null;
}

export interface WaitItem {
	id: string;
	kind: 'decision' | 'need' | 'date' | 'failure' | 'signals' | 'report' | 'raise' | 'finding';
	title: string;
	href: string;
	due: string | null;
	overdue: boolean;
}

export interface TodayData {
	overview: OverviewLevel;
	counts: Counts;
	/** Every wait, oldest due first; Today lists the first five. */
	waits: WaitItem[];
	/** How many waits there are, where the surface said more than it listed. */
	waits_total: number;
	/** The destinations that wait for the reader: the navigation's marks. */
	marks: string[];
	/** The operation's own sentence: that it runs as expected, or what needs a look (ADR-0121). */
	operation: string | null;
	/** The governance lines, for the section that says what governs the work. */
	lines: Line[];
	/** Reads that failed, by what they read: said on the page, never shown as nothing. */
	failed: string[];
	/** Whether the surface's own summary answered, or the older reads were put together. */
	source: 'today' | 'composed';
}

/** `GET /levels/today` as the surface sends it. Every field but the overview may be missing. */
interface TodayAnswer {
	overview: OverviewLevel;
	counts?: Partial<Counts>;
	waits?: Partial<WaitItem>[];
	waits_total?: number;
	marks?: string[];
	lines?: Line[];
	operation?: string;
}

function count(found: Partial<Counts> | undefined, key: keyof Counts): number | null {
	const value = found?.[key];
	return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Oldest due first; one past its date before one that is not. */
export function byDue(a: WaitItem, b: WaitItem): number {
	if (a.overdue !== b.overdue) return a.overdue ? -1 : 1;
	return (a.due ?? '￿').localeCompare(b.due ?? '￿') || a.id.localeCompare(b.id);
}

/** The waits from the decision requests and the open reports, each once by its identifier. */
export function waitsOf(requests: AddressedRequest[], reports: ReportList['reports']): WaitItem[] {
	const found = new Map<string, WaitItem>();
	for (const r of requests) {
		found.set(r.id, {
			id: r.id,
			kind: 'decision',
			title: r.request.question,
			href: requestsLink(r.id),
			due: r.request.due ?? null,
			overdue: r.overdue
		});
	}
	for (const r of openReports(reports)) {
		if (found.has(r.id)) continue;
		found.set(r.id, { id: r.id, kind: r.kind, title: r.title, href: reportLink(r.id), due: r.due ?? null, overdue: false });
	}
	return [...found.values()].sort(byDue);
}

/** A raise of a level or a finding in review that waits for the reader: one item each, leading to
 * its page. Decision requests and needs are items of their own already. */
export function linesThatWait(lines: Line[]): WaitItem[] {
	return lines
		.filter((l) => l.waiting && (l.kind === 'autonomy' || l.kind === 'findings'))
		.map((l) => ({ id: l.kind, kind: l.kind === 'autonomy' ? 'raise' : 'finding', title: l.text, href: l.href, due: null, overdue: false }));
}

function fromSurface(body: TodayAnswer): TodayData {
	const waits = (body.waits ?? [])
		.filter((w): w is Partial<WaitItem> & { id: string; title: string } => typeof w.id === 'string' && typeof w.title === 'string')
		.map((w) => ({
			id: w.id,
			kind: w.kind ?? 'report',
			title: w.title,
			href: w.href ?? (w.kind === 'decision' ? requestsLink(w.id) : reportLink(w.id)),
			due: w.due ?? null,
			overdue: w.overdue ?? false
		}));
	return {
		overview: body.overview,
		counts: {
			waiting_for_you: count(body.counts, 'waiting_for_you'),
			running: count(body.counts, 'running'),
			waiting_on_person: count(body.counts, 'waiting_on_person'),
			failed_24h: count(body.counts, 'failed_24h'),
			incidents: count(body.counts, 'incidents'),
			alerts: count(body.counts, 'alerts')
		},
		waits,
		waits_total: typeof body.waits_total === 'number' ? body.waits_total : waits.length,
		marks: Array.isArray(body.marks) ? body.marks : [],
		operation: typeof body.operation === 'string' ? body.operation : null,
		lines: Array.isArray(body.lines) ? body.lines : [],
		failed: [],
		source: 'today'
	};
}

/** Today from the reads that existed before the summary. The overview is the page; the rest
 * fills what it can, and a read that failed is named. */
async function composed(base: URL, overview: OverviewLevel, administrationKey: string | null, fetcher: typeof fetch): Promise<TodayData> {
	const [operation, requests, reports, lines] = await Promise.all([
		readShared<OperationSummary>(base, 'operation', fetcher),
		readShared<{ requests: AddressedRequest[] }>(base, 'decisions', fetcher),
		readShared<ReportList>(base, 'owner/reports', fetcher),
		governanceLines(base, administrationKey, fetcher)
	]);
	const failed: string[] = [];
	const broke = (answer: Answer<unknown>, what: string) => {
		if (!answer.ok && (answer.problem.status === 0 || answer.problem.status >= 500)) failed.push(what);
	};
	broke(operation, 'what keeps the operation running');
	broke(requests, 'the decision requests');
	broke(reports, 'the reports');
	const waits = [...waitsOf(requests.ok ? requests.body.requests : [], reports.ok ? reports.body.reports : []), ...linesThatWait(lines)];
	const answered = requests.ok || reports.ok;
	const op = operation.ok ? operation.body : null;
	return {
		overview,
		counts: {
			waiting_for_you: answered ? waits.length : null,
			running: overview.areas.reduce((n, a) => n + a.working, 0),
			waiting_on_person: null,
			failed_24h: null,
			incidents: op ? op.incidents.open : null,
			alerts: op && op.alerts.readable ? op.alerts.in_effect : null
		},
		waits,
		waits_total: waits.length,
		marks: [...waitingDestinations(lines, op ? operationLines(op) : [])],
		operation: op ? operationSentence(op) : null,
		lines,
		failed,
		source: 'composed'
	};
}

export type TodayRead = { ok: true; today: TodayData } | { ok: false; problem: Problem };

/** Whether the surface serves its summary: unknown until asked, and not asked again in this
 * visit once it answered that it does not. */
let served: boolean | null = null;

/** Today, from the surface's summary where it is served, put together otherwise. */
export async function readToday(base: URL, administrationKey: string | null, fetcher: typeof fetch = fetch): Promise<TodayRead> {
	if (served !== false) {
		const summary = await readShared<TodayAnswer>(base, 'levels/today', fetcher);
		if (summary.ok && summary.body && typeof summary.body === 'object' && summary.body.overview) {
			served = true;
			const today = fromSurface(summary.body);
			if (today.lines.length === 0) today.lines = await governanceLines(base, administrationKey, fetcher);
			return { ok: true, today };
		}
		if (!summary.ok && summary.problem.status === 401) return { ok: false, problem: summary.problem };
		if (!summary.ok && (summary.problem.status === 404 || summary.problem.status === 405)) served = false;
	}
	const overview = await readShared<OverviewLevel>(base, 'levels/overview', fetcher);
	if (!overview.ok) return { ok: false, problem: overview.problem };
	return { ok: true, today: await composed(base, overview.body, administrationKey, fetcher) };
}

/** Forgets whether the surface serves its summary: for a test, or a new sign-in. */
export function forgetServed(): void {
	served = null;
}
