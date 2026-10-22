// What keeps the operation running (ADR-0121, issue #562). Each page is drawn from the
// surface's own answer — `fixtures.operation`, written by `make generate` with the functions
// the routes answer with — opens with its own sentence, links every run, step and process its
// records name, and names no person.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import AlertsView from './AlertsView.svelte';
import BackupView from './BackupView.svelte';
import fixtures from './generated/fixtures.json';
import IncidentsView from './IncidentsView.svelte';
import { processLink, runLink } from './links';
import {
	alertsLink,
	backupLink,
	incidentsLink,
	operationLines,
	operationSentence,
	signalsLink,
	webAddress,
	type AlertRecord,
	type BackupRecord,
	type DailyReport,
	type IncidentRecord,
	type OperationSummary,
	type SignalRecord
} from './operation';
import OperationLines from './OperationLines.svelte';
import SignalsView from './SignalsView.svelte';

const ANSWERS = fixtures.operation;
const SUMMARY = ANSWERS.summary as unknown as OperationSummary;
const WITHHELD = ANSWERS.summary_withheld as unknown as OperationSummary;
const INCIDENTS = ANSWERS.incidents.incidents as unknown as IncidentRecord[];
const ALERTS = ANSWERS.alerts.alerts as unknown as AlertRecord[];
const BACKUP = ANSWERS.backup as unknown as BackupRecord;
const SIGNALS = ANSWERS.signals.signals as unknown as SignalRecord[];
const DAILY = ANSWERS.daily_report as unknown as DailyReport;

function attr(text: string): string {
	return text.replaceAll('&', '&amp;');
}

/** The heading's text: the first `<h1>` of the page. */
function heading(html: string): string {
	return /<h1[^>]*>([^<]*)<\/h1>/.exec(html)?.[1] ?? '';
}

/** The first line of the page's text equivalent. */
function firstText(html: string): string {
	return /<li data-text="sentence">([^<]*)<\/li>/.exec(html)?.[1] ?? '';
}

function hrefs(html: string): string[] {
	return [...html.matchAll(/href="([^"]*)"/g)].map((m) => m[1]!);
}

describe('the start page', () => {
	it('carries one line per kind, each leading to its page', () => {
		const lines = operationLines(SUMMARY);
		expect(lines.map((l) => [l.kind, l.href])).toEqual([
			['incidents', incidentsLink],
			['alerts', alertsLink],
			['backup', backupLink],
			['signals', signalsLink]
		]);
		const html = render(OperationLines, { props: { summary: SUMMARY } }).body;
		for (const l of lines) expect(hrefs(html)).toContain(l.href);
	});

	it('says how many are open or red, as the surface counted them', () => {
		const text = Object.fromEntries(operationLines(SUMMARY).map((l) => [l.kind, l.text]));
		expect(text.incidents).toBe(`${SUMMARY.incidents.open} incident open of ${SUMMARY.incidents.total}.`);
		expect(text.alerts).toBe('2 alerts in effect of 2.');
		expect(text.backup).toBe('Failing.');
		expect(text.signals).toBe('1 red, 1 yellow, 1 not measured, of 3. Newest daily report: signals-2026-10-22.');
	});

	it('opens with its own sentence: what needs a look', () => {
		const html = render(OperationLines, { props: { summary: SUMMARY } }).body;
		const sentence = operationSentence(SUMMARY);
		expect(sentence).toBe('Incidents, Alerts, Backup, Signals need a look.');
		const first = /<p class="sentence[^"]*" data-text="operation">([^<]*)<\/p>/.exec(html)?.[1];
		expect(first).toBe(sentence);
		expect(html.indexOf(sentence)).toBeLessThan(html.indexOf('<ul'));
	});

	it('gives no figure of what the reader may not read', () => {
		const text = Object.fromEntries(operationLines(WITHHELD).map((l) => [l.kind, l.text]));
		for (const kind of ['alerts', 'backup']) {
			expect(text[kind]).toBe('Read by the owner and the people the owner named.');
		}
		expect(text.signals).not.toContain('daily report');
	});
});

describe('the incidents', () => {
	const html = render(IncidentsView, { props: { incidents: INCIDENTS } }).body;

	it('open with their own sentence, also the first line of the text', () => {
		expect(heading(html)).toBe('1 incident is open: an expected run did not happen, or did not end in time.');
		expect(firstText(html)).toBe(heading(html));
	});

	it('link the process, the run and the last run each one names', () => {
		for (const i of INCIDENTS) {
			expect(hrefs(html)).toContain(attr(processLink(i.process_version)));
			if (i.run_id) expect(hrefs(html)).toContain(runLink(i.run_id));
			if (i.last_run?.run_id) expect(hrefs(html)).toContain(runLink(i.last_run.run_id));
		}
	});

	it('show the open ones first, each with what was expected', () => {
		expect(html.indexOf('data-incident="inc_missing"')).toBeLessThan(html.indexOf('data-incident="inc_overdue"'));
		expect(html).toContain('2026-10-22 07:00 UTC');
	});
});

describe('the alerts', () => {
	const html = render(AlertsView, { props: { alerts: ALERTS } }).body;

	it('open with their own sentence', () => {
		expect(heading(html)).toBe('2 things need a person’s action.');
		expect(firstText(html)).toBe(heading(html));
	});

	it('link the runs an alert is about, and the backup for the backup alert', () => {
		const about = ALERTS.flatMap((a) => a.about).filter((r) => r.run_id);
		expect(about.length).toBeGreaterThan(0);
		for (const r of about) expect(hrefs(html)).toContain(runLink(r.run_id!));
		expect(hrefs(html)).toContain(backupLink);
	});

	it('say what became of each report', () => {
		for (const a of ALERTS) expect(html).toContain(attr(a.state));
	});
});

describe('the backup', () => {
	const html = render(BackupView, { props: { backup: BACKUP } }).body;

	it('opens with its own sentence', () => {
		expect(heading(html)).toBe('The backup is failing: 1 run failed since the last success.');
		expect(firstText(html)).toBe(heading(html));
	});

	it('names its last success, its newest failure, and by when the next is due', () => {
		expect(html).toContain(BACKUP.last_ok!.name);
		expect(html).toContain(BACKUP.newest_failed!.name);
		expect(html).toContain('2026-10-22 04:00 UTC');
		expect(html).toContain('data-standing="failing"');
	});
});

describe('the signals', () => {
	const html = render(SignalsView, { props: { signals: SIGNALS, daily: DAILY } }).body;

	it('open with their own sentence', () => {
		expect(heading(html)).toBe('1 red, 1 yellow, 1 not measured of 3 signals.');
		expect(firstText(html)).toBe(heading(html));
	});

	it('show red first and link the run, the process and the case of each measured signal', () => {
		expect(html.indexOf('data-level="red"')).toBeLessThan(html.indexOf('data-level="yellow"'));
		expect(html.indexOf('data-level="yellow"')).toBeLessThan(html.indexOf('data-level="unmeasured"'));
		for (const s of SIGNALS) {
			if (s.run_id) expect(hrefs(html)).toContain(runLink(s.run_id));
			expect(hrefs(html)).toContain(attr(processLink(s.process_version ?? s.process)));
			expect(hrefs(html)).toContain(s.case);
		}
	});

	it('show the newest daily report, or who reads it', () => {
		expect(html).toContain(`data-daily="${DAILY.id}"`);
		for (const line of DAILY.needed) expect(html).toContain(line);
		const withheld = render(SignalsView, {
			props: { signals: SIGNALS, dailyNote: 'The owner and the people the owner named read the daily report.' }
		}).body;
		expect(withheld).toContain('The owner and the people the owner named read the daily report.');
	});

	it('make a case a link only where it is a web address', () => {
		expect(webAddress('https://tracker.example/cases/1')).toBe('https://tracker.example/cases/1');
		expect(webAddress('javascript:alert(1)')).toBeNull();
	});
});

describe('every page', () => {
	it('names no person', () => {
		const pages = [
			render(OperationLines, { props: { summary: SUMMARY } }).body,
			render(IncidentsView, { props: { incidents: INCIDENTS } }).body,
			render(AlertsView, { props: { alerts: ALERTS } }).body,
			render(BackupView, { props: { backup: BACKUP } }).body,
			render(SignalsView, { props: { signals: SIGNALS, daily: DAILY } }).body
		];
		for (const html of pages) expect(html).not.toMatch(/idn_/);
	});
});
