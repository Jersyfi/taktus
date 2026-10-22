// What keeps the operation running (ADR-0121, DEC-0218): the shapes the surface answers, where
// each page lives, and the sentence each page opens with (UC-6.10). Every figure in a sentence
// is one the surface handed over; nothing is counted here that the surface did not count.

/** `GET /operation`: one entry per kind. A kind the reader may not read carries no figure. */
export interface OperationSummary {
	tenant: string;
	incidents: { readable: true; open: number; total: number };
	signals: { readable: true; red: number; yellow: number; unmeasured: number; total: number };
	alerts: { readable: false } | { readable: true; in_effect: number; total: number };
	backup: { readable: false } | { readable: true; standing: BackupStanding; next_due: string | null };
	daily_report: { readable: false } | { readable: true; id: string | null; title: string | null };
}

/** One event of an incident's timeline. */
export interface IncidentEvent {
	at: string;
	what: 'missed' | 'happened' | 'closed' | 'red';
	expected_at: string | null;
	deadline: string | null;
	run_id: string | null;
}

/** An incident (ADR-0107): what was expected and what happened. It names no person. */
export interface IncidentRecord {
	id: string;
	kind: string;
	state: 'open' | 'closed';
	process_id: string;
	process_version: string;
	rule: string;
	raised_at: string;
	expected_at: string | null;
	closed_at: string | null;
	run_id: string | null;
	step_id: string | null;
	last_run: { at: string; run_id: string | null; kind: string } | null;
	facts: Record<string, string | number | null>;
	timeline: IncidentEvent[];
}

/** What an alert is about: a run, a step of it, a process version. */
export interface AlertAbout {
	run_id?: string;
	step_id?: string;
	process_version?: string;
}

/** An alert with what became of its report (ADR-0106). */
export interface AlertRecord {
	id: string;
	kind: string;
	since: string;
	in_effect: boolean;
	closed: boolean;
	delivered: boolean;
	reason: string | null;
	state: string;
	title: string;
	summary: string;
	needed: string[];
	steps: string[];
	standing_still: string[];
	about: AlertAbout[];
	report: boolean;
}

export type BackupStanding = 'ok' | 'failing' | 'missing' | 'not_recorded';

/** `GET /backup`. */
export interface BackupRecord {
	standing: BackupStanding;
	watched: boolean;
	expected_hours: number | null;
	next_due: string | null;
	last_ok: { name: string; at: string } | null;
	failed_count: number;
	newest_failed: { name: string; at: string; reason: string | null } | null;
	alert: { id: string; title: string; summary: string; needed: string[]; steps: string[] } | null;
}

export type SignalLevel = 'normal' | 'yellow' | 'red' | 'unmeasured';

/** A signal judged now, beside its corridor (ADR-0109). It names a role or a department. */
export interface SignalRecord {
	signal: string;
	corridor: string;
	version: number;
	process: string;
	step: string;
	select: string | null;
	about: { kind: 'operation' | 'role' | 'department'; name: string | null };
	bounds: 'median' | 'fixed';
	direction: 'above' | 'below';
	yellow: number;
	red: number;
	window_seconds: number;
	minimum: number;
	fresh_seconds: number;
	role: string;
	case: string;
	interventions: string[];
	changed_at: string;
	level: SignalLevel;
	reason: string | null;
	value: number | null;
	median: number | null;
	yellow_at: number | null;
	red_at: number | null;
	run_id: string | null;
	step_id: string | null;
	process_version: string | null;
	at: string | null;
}

/** `GET /signals/daily-report`: the newest report of kind `signals`, as its view. */
export interface DailyReport {
	id: string;
	title: string;
	needed: string[];
	steps: string[];
	standing_still: string[];
	due: string;
	raised_at: string;
	links?: { label: string; url: string }[];
}

export const incidentsLink = '#/incidents';
export const alertsLink = '#/alerts';
export const backupLink = '#/backup';
export const signalsLink = '#/signals';

/** A case's address as a link only where it is a web address: a corridor's case is configured
 * text, and nothing else is ever made a link. */
export function webAddress(address: string): string | null {
	return /^https?:\/\//i.test(address) ? address : null;
}

function count(n: number, one: string, many: string): string {
	return `${n === 0 ? 'No' : n} ${n === 1 ? one : many}`;
}

/** A moment as a person reads it, in UTC: `2026-10-22 09:00 UTC`. */
export function moment(iso: string | null | undefined): string {
	if (!iso) return 'unknown';
	const at = new Date(iso);
	if (Number.isNaN(at.getTime())) return iso;
	return `${at.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export function incidentsSentence(incidents: IncidentRecord[]): string {
	const open = incidents.filter((i) => i.state === 'open').length;
	if (incidents.length === 0) return 'No incident was raised: every expected run happened.';
	if (open === 0) {
		const n = incidents.length;
		return `No incident is open; ${n} ${n === 1 ? 'was' : 'were'} closed.`;
	}
	return `${count(open, 'incident is', 'incidents are')} open: an expected run did not happen, or did not end in time.`;
}

export function alertsSentence(alerts: AlertRecord[]): string {
	const open = alerts.filter((a) => a.in_effect && !a.closed).length;
	if (open === 0) return 'Nothing needs a person’s action.';
	return `${count(open, 'thing needs', 'things need')} a person’s action.`;
}

export function backupSentence(backup: BackupRecord): string {
	switch (backup.standing) {
		case 'failing':
			return `The backup is failing: ${count(backup.failed_count, 'run', 'runs')} failed since the last success.`;
		case 'missing':
			return `No backup succeeded in the last ${backup.expected_hours} hours.`;
		case 'ok':
			return backup.next_due
				? `The last backup succeeded; the next is due by ${moment(backup.next_due)}.`
				: 'The last backup succeeded.';
		default:
			return 'No backup was recorded yet.';
	}
}

export function signalsSentence(signals: SignalRecord[]): string {
	if (signals.length === 0) return 'No signal is measured: no corridor is in force.';
	const red = signals.filter((s) => s.level === 'red').length;
	const yellow = signals.filter((s) => s.level === 'yellow').length;
	const unmeasured = signals.filter((s) => s.level === 'unmeasured').length;
	if (red + yellow + unmeasured === 0) return `Every signal is within its corridor (${signals.length} measured).`;
	const parts: string[] = [];
	if (red) parts.push(`${red} red`);
	if (yellow) parts.push(`${yellow} yellow`);
	if (unmeasured) parts.push(`${unmeasured} not measured`);
	return `${parts.join(', ')} of ${signals.length} ${signals.length === 1 ? 'signal' : 'signals'}.`;
}

/** One line of the start page. `red` marks a kind that needs a look. */
export interface OperationLine {
	kind: 'incidents' | 'alerts' | 'backup' | 'signals';
	label: string;
	text: string;
	href: string;
	red: boolean;
}

export function operationLines(summary: OperationSummary): OperationLine[] {
	const lines: OperationLine[] = [];
	const { incidents, signals, alerts, backup, daily_report } = summary;
	lines.push({
		kind: 'incidents',
		label: 'Incidents',
		text: `${count(incidents.open, 'incident', 'incidents')} open of ${incidents.total}.`,
		href: incidentsLink,
		red: incidents.open > 0
	});
	lines.push({
		kind: 'alerts',
		label: 'Alerts',
		text: alerts.readable
			? `${count(alerts.in_effect, 'alert', 'alerts')} in effect of ${alerts.total}.`
			: 'Read by the owner and the people the owner named.',
		href: alertsLink,
		red: alerts.readable && alerts.in_effect > 0
	});
	lines.push({
		kind: 'backup',
		label: 'Backup',
		text: backup.readable ? backupLine(backup.standing, backup.next_due) : 'Read by the owner and the people the owner named.',
		href: backupLink,
		red: backup.readable && (backup.standing === 'failing' || backup.standing === 'missing')
	});
	const deviating = signals.red + signals.yellow + signals.unmeasured;
	const daily = daily_report.readable && daily_report.id ? ` Newest daily report: ${daily_report.id}.` : '';
	lines.push({
		kind: 'signals',
		label: 'Signals',
		text:
			(signals.total === 0
				? 'No corridor is in force.'
				: deviating === 0
					? `All ${signals.total} within their corridors.`
					: `${signals.red} red, ${signals.yellow} yellow, ${signals.unmeasured} not measured, of ${signals.total}.`) + daily,
		href: signalsLink,
		red: signals.red > 0
	});
	return lines;
}

function backupLine(standing: BackupStanding, nextDue: string | null): string {
	switch (standing) {
		case 'failing':
			return 'Failing.';
		case 'missing':
			return 'Missing: none succeeded within the expected interval.';
		case 'ok':
			return nextDue ? `Succeeded; the next is due by ${moment(nextDue)}.` : 'Succeeded.';
		default:
			return 'None recorded.';
	}
}

/** The start page's own sentence: what needs a look, before the lines (UC-6.10). */
export function operationSentence(summary: OperationSummary): string {
	const red = operationLines(summary).filter((l) => l.red);
	if (red.length === 0) return 'The operation runs as expected.';
	return `${red.map((l) => l.label).join(', ')} ${red.length === 1 ? 'needs' : 'need'} a look.`;
}
