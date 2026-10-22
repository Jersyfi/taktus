// What governs the work, as the surface answers it (ADR-0122, DEC-0218): each process's level and
// its correction rates (`GET /autonomy`), the instance's findings and their review
// (`GET /findings`), the needs among the reports to the owner (`GET /owner/reports`), and the
// tenants for an administrator (`GET /administration/tenants`). The pages show what they are
// handed; nothing here computes a figure.

import { read, readAs, send, type Answer } from './api';

// --- the shapes the surface answers --------------------------------------------------------------

export interface RateWindow {
	days: number;
	since: string;
	decided: number;
	released: number;
	corrected: number;
	rejected: number;
	/** Corrected and rejected over all decided; null where nothing was decided. */
	rate: number | null;
}

/** A process, or one action class of it: counted per process and action, never per person. */
export interface CorrectionUnit {
	action: string | null;
	level: number;
	week: RateWindow;
	month: RateWindow;
	text: string;
	counted_since?: string;
	changed_at?: string;
}

export interface Lowering {
	incident: string;
	rule: string;
	raised_at: string;
	run: string | null;
	unit?: string | null;
	level_before?: string | null;
	level_after?: string | null;
	facts: Record<string, string | number | null>;
}

export interface RaiseProposed {
	action: string | null;
	version: string;
	at: string;
	week: RateWindow;
	month: RateWindow;
}

export interface ProcessAutonomy {
	id: string;
	name: string;
	version: string;
	stated: { level: number; reason: string; toward_next?: string };
	stated_text: string;
	lowered: { level?: number | null; actions: Record<string, number> };
	in_force: number;
	text: string;
	lowerings: Lowering[];
	units: CorrectionUnit[];
	raises_proposed: RaiseProposed[];
}

export interface AutonomyAnswer {
	summary: string;
	processes: ProcessAutonomy[];
	limits: {
		raise_decisions: number;
		raise_weeks: number;
		raise_rate: number;
		lower_rate: number;
		lower_window_days: number;
		lower_minimum: number;
		shipped_default: boolean;
	};
}

export interface FindingDocument {
	lack: { key: string; cause: string; lacking: string };
	title: string;
	/** `product`, `configuration`, `own`, or `local_for_us`. */
	kind: string;
	classified: { kind: string; adapters: string[] };
	local_for_us: boolean;
	leaves: boolean;
	in_review: boolean;
	occurrences: { run: string; step: string; since: string; seconds: number | null }[];
	waited_seconds: number;
	text: string;
	withheld: { kind: string; excerpt: string }[];
	said: string;
}

export interface FindingsAnswer {
	level: 'off' | 'review' | 'automatic';
	summary: string;
	in_review: number;
	findings: FindingDocument[];
}

export type ReviewChoice = 'send' | 'not' | 'local';

/** An answer in review, read back: nothing was done yet (ADR-0008). */
export interface ReviewReading {
	lack: string;
	answer: ReviewChoice;
	reading: string;
	text: string;
	confirmation: string;
}

export interface ReviewDone {
	done: boolean;
	answer: ReviewChoice;
	message: string;
}

/** A report to the owner as `GET /owner/reports` answers it (ADR-0045); a need is one kind. */
export interface OwnerReport {
	id: string;
	kind: string;
	title: string;
	needed: string[];
	steps: string[];
	standing_still: string[];
	due: string;
	offered: { id: string; label: string; recommended?: boolean }[];
	raised_at: string;
	state: 'open' | 'reflected' | 'filed';
	reading?: { answer: string; kept: boolean; at: string; by_you: boolean };
	filed?: { answer: string; at: string; by_you: boolean; record?: string; where?: string };
	links?: { label: string; url: string }[];
	history: { at: string; event: string; by_you: boolean }[];
}

export interface Tenant {
	id: string;
	name: string;
	created_at: string;
}

// --- where each page lives -----------------------------------------------------------------------

export const NEEDS = '#/needs';
export const AUTONOMY = '#/autonomy';
export const FINDINGS = '#/findings';
export const TENANTS = '#/tenants';

// --- reads and answers ---------------------------------------------------------------------------

/** The needs among the reports, the open ones first, as the surface ordered them. */
export function needsOf(reports: OwnerReport[]): OwnerReport[] {
	return reports.filter((r) => r.kind === 'need');
}

/** An answer in review, sent to be read back. It changes nothing on the instance. */
export function readBack(
	base: URL,
	lack: string,
	answer: ReviewChoice,
	fetcher: typeof fetch = fetch
): Promise<Answer<ReviewReading>> {
	return send<ReviewReading>(base, `findings/${encodeURIComponent(lack)}/review`, { answer }, fetcher);
}

/** The reading confirmed or rejected: only a confirmation of what was read back acts. */
export function confirmReading(
	base: URL,
	reading: ReviewReading,
	confirmed: boolean,
	fetcher: typeof fetch = fetch
): Promise<Answer<ReviewDone>> {
	return send<ReviewDone>(
		base,
		`findings/${encodeURIComponent(reading.lack)}/review/confirm`,
		{ answer: reading.answer, confirmation: reading.confirmation, confirmed },
		fetcher
	);
}

/** A tenant created (`POST`) or renamed (`PATCH`), with the administration key (ADR-0104). A
 * refusal is the surface's problem, never thrown. */
export async function writeTenant(
	base: URL,
	administrationKey: string,
	name: string,
	id: string | null,
	fetcher: typeof fetch = fetch
): Promise<Answer<Tenant>> {
	const path = id === null ? 'administration/tenants' : `administration/tenants/${encodeURIComponent(id)}`;
	const response = await fetcher(new URL(path, base), {
		method: id === null ? 'POST' : 'PATCH',
		headers: { Authorization: `Bearer ${administrationKey}`, Accept: 'application/json', 'Content-Type': 'application/json' },
		body: JSON.stringify({ name })
	});
	if (response.ok) return { ok: true, body: (await response.json()) as Tenant };
	let problem = { status: response.status, title: response.statusText, detail: '' };
	try {
		problem = { ...problem, ...((await response.json()) as Partial<typeof problem>) };
	} catch {
		// A body that is no problem document: the status says enough.
	}
	return { ok: false, problem };
}

// --- the start page: one line per kind ------------------------------------------------------------

export interface Line {
	kind: 'requests' | 'needs' | 'autonomy' | 'findings' | 'tenants';
	href: string;
	/** What the line says: how many are open or waiting. */
	text: string;
	/** Whether something waits for the reader. */
	waiting: boolean;
}

function plural(n: number, one: string, many: string): string {
	return `${n} ${n === 1 ? one : many}`;
}

/** One line per kind the reader may see. A kind the surface refuses the reader is left out. */
export async function governanceLines(
	base: URL,
	administrationKey: string | null,
	fetcher: typeof fetch = fetch
): Promise<Line[]> {
	const [requests, reports, autonomy, findings, tenants] = await Promise.all([
		read<{ requests: unknown[]; overdue: number }>(base, 'decisions', fetcher),
		read<{ reports: OwnerReport[] }>(base, 'owner/reports', fetcher),
		read<AutonomyAnswer>(base, 'autonomy', fetcher),
		read<FindingsAnswer>(base, 'findings', fetcher),
		administrationKey
			? readAs<{ tenants: Tenant[] }>(base, 'administration/tenants', administrationKey, fetcher)
			: Promise.resolve(null)
	]);
	const lines: Line[] = [];
	if (requests.ok) {
		const n = requests.body.requests.length;
		lines.push({
			kind: 'requests',
			href: '#/requests',
			text: `Decision requests: ${n === 0 ? 'none waits for you' : `${plural(n, 'waits', 'wait')} for you`}${requests.body.overdue ? `, ${requests.body.overdue} past its date` : ''}.`,
			waiting: n > 0
		});
	}
	if (reports.ok) {
		const open = needsOf(reports.body.reports).filter((r) => r.state !== 'filed').length;
		lines.push({
			kind: 'needs',
			href: NEEDS,
			text: `Needs: ${open === 0 ? 'none open' : `${plural(open, 'is', 'are')} open`}.`,
			waiting: open > 0
		});
	}
	if (autonomy.ok) {
		const below = autonomy.body.processes.filter((p) => p.in_force < p.stated.level).length;
		const raises = autonomy.body.processes.reduce((n, p) => n + p.raises_proposed.length, 0);
		const parts = [`${plural(below, 'process runs', 'processes run')} below the stated level`];
		if (raises) parts.push(`${plural(raises, 'raise waits', 'raises wait')} for a person`);
		lines.push({ kind: 'autonomy', href: AUTONOMY, text: `Levels and corrections: ${parts.join(', ')}.`, waiting: below + raises > 0 });
	}
	if (findings.ok) {
		const n = findings.body.findings.length;
		const waiting = findings.body.in_review;
		lines.push({
			kind: 'findings',
			href: FINDINGS,
			text: `Findings: ${plural(n, 'lack', 'lacks')} met${findings.body.level === 'review' ? `, ${plural(waiting, 'waits', 'wait')} for a review` : ''}.`,
			waiting: waiting > 0
		});
	}
	if (tenants && tenants.ok) {
		lines.push({
			kind: 'tenants',
			href: TENANTS,
			text: `Tenants: this instance serves ${tenants.body.tenants.length}.`,
			waiting: false
		});
	} else if (!administrationKey) {
		lines.push({ kind: 'tenants', href: TENANTS, text: 'Tenants: for the holder of the administration key.', waiting: false });
	}
	return lines;
}

// --- the administration key, for the tab's session only (ADR-0104) --------------------------------

const ADMINISTRATION = 'taktus.administration';
let administration: string | null = null;

function storage(): Storage | null {
	try {
		return typeof sessionStorage === 'undefined' ? null : sessionStorage;
	} catch {
		return null;
	}
}

/** The instance's administration key, as given in this tab; it is not an account key. */
export function currentAdministrationKey(): string | null {
	if (administration !== null) return administration;
	try {
		administration = storage()?.getItem(ADMINISTRATION) ?? null;
	} catch {
		administration = null;
	}
	return administration;
}

export function keepAdministrationKey(key: string): void {
	administration = key.trim() || null;
	try {
		if (administration === null) storage()?.removeItem(ADMINISTRATION);
		else storage()?.setItem(ADMINISTRATION, administration);
	} catch {
		// Kept in memory only.
	}
}
