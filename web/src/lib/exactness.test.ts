// The exactness statement where its reader is (UC-6.9 §1, #224): the process page and every run
// show the statement of the version they show, with all four parts, and the overview shows it
// per process. Every sentence is drawn as it was handed over: no view edits, shortens or
// rewrites it.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import fixtures from './generated/fixtures.json';
import OverviewView from './OverviewView.svelte';
import ProcessView from './ProcessView.svelte';
import RunView from './RunView.svelte';
import type { ExactnessStatement, OverviewLevel, ProcessLevel, RunLevel } from './types';

const PROCESS = fixtures.process_level as unknown as ProcessLevel;
const RUN = fixtures.run_level as unknown as RunLevel;
const OVERVIEW = fixtures.overview as unknown as OverviewLevel;
const PARTS = ['Which checks apply', 'What they cover', 'What they do not cover', 'The residual risk'];

function escaped(text: string): string {
	return text
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#39;');
}

function holdsEverySentence(html: string, statement: ExactnessStatement): void {
	expect(statement.parts.map((p) => p.title)).toEqual(PARTS);
	for (const part of statement.parts) {
		expect(html).toMatch(new RegExp(`<h3[^>]*>${part.title}</h3>`));
		for (const line of part.lines) {
			const shown = html.includes(line) || html.includes(escaped(line));
			expect(shown, line).toBe(true);
		}
	}
}

describe('the exactness statement', () => {
	it('is on the process page, with all four parts, as generated', () => {
		const statement = PROCESS.exactness!;
		const { body } = render(ProcessView, { props: { level: PROCESS, motionAllowed: false } });
		expect(body).toContain(`data-exactness-statement="${statement.process_version}"`);
		holdsEverySentence(body, statement);
	});

	it('is on every run, the statement of the version it executes', () => {
		const statement = RUN.exactness!;
		const { body } = render(RunView, { props: { level: RUN, motionAllowed: false } });
		holdsEverySentence(body, statement);
	});

	it('is on the overview per process, folded behind its title', () => {
		const process = OVERVIEW.areas[0]!.processes.find((p) => p.exactness)!;
		const { body } = render(OverviewView, { props: { level: OVERVIEW, motionAllowed: false } });
		expect(body).toMatch(/<details[^>]*>/);
		holdsEverySentence(body, process.exactness!);
	});

	it('is absent, never invented, where the surface hands none over', () => {
		const level = { ...PROCESS, exactness: null };
		const { body } = render(ProcessView, { props: { level, motionAllowed: false } });
		expect(body).not.toContain('data-exactness-statement');
	});
});
