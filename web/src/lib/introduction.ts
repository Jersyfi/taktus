// A tenant's introduction in stages (ADR-0137, ADR-0191): `GET /stages`, read by the holders of
// the plan's responsible role, and `POST /stages/{id}/open`, the one act on the page. Every figure
// is the surface's, computed from the ledger when it was asked; nothing here counts. No figure
// names a person: the page names stages, processes and roles.

export type StageState = 'closed' | 'open' | 'holding' | 'not_holding';

export interface ProcessEvidence {
	process: string;
	version?: string | null;
	level?: number | null;
	granted: number;
	runs: number;
	missed: number;
	incidents: number;
	last_finished?: string | null;
}

export interface StageFigures {
	since: string;
	until: string;
	weeks: number;
	runs: number;
	missed: number;
	incidents: number;
	correction_rate?: number | null;
	undecided: number;
	reports_missed: number;
}

export interface StageDocument {
	stage: { id: string; name: string; processes: Record<string, number> };
	position: number;
	state: StageState;
	opened_at?: string | null;
	holds: boolean;
	figures?: StageFigures | null;
	missing: string[];
	proposed: boolean;
	processes: ProcessEvidence[];
	/** The condition in words, one figure per line. */
	condition: string[];
	/** One sentence: where the stage stands. */
	text: string;
}

/** `GET /stages`. */
export interface Introduction {
	summary: string;
	stages: StageDocument[];
}

const STATES: Record<StageState, string> = {
	closed: 'Not open',
	open: 'Open, not holding yet',
	holding: 'Holding',
	not_holding: 'No longer holding'
};

export function stateLabel(state: StageState): string {
	return STATES[state];
}

/** Whether the rule lets the reader open the stage now: it is not open, and its opening lacks
 * nothing the surface named. The surface decides again when it is asked, and says why it
 * refuses. */
export function mayOpen(stage: StageDocument): boolean {
	return stage.state === 'closed' && stage.missing.length === 0;
}

/** One process of a stage in words: its version and level, what it is granted, and what it did
 * within the stage's window. */
export function processLine(p: ProcessEvidence, open: boolean): string {
	const runs = p.version ? `${p.version} at level ${p.level ?? '–'}` : 'not running for the tenant';
	const granted = `granted level ${p.granted}`;
	if (!open) return `${p.process}: ${runs}, ${granted}.`;
	return `${p.process}: ${runs}, ${granted}; ${p.runs} ${p.runs === 1 ? 'run' : 'runs'}, ${p.missed} missed, ${p.incidents} ${p.incidents === 1 ? 'incident' : 'incidents'}.`;
}

/** The figures the rule read for an open stage, in words. */
export function figuresLine(f: StageFigures): string {
	const rate = f.correction_rate == null ? '' : `, correction rate ${Math.round(f.correction_rate * 100)}%`;
	return `Over ${f.weeks.toFixed(1)} weeks: ${f.runs} runs, ${f.missed} missed, ${f.incidents} incidents${rate}, ${f.undecided} waiting for a person, ${f.reports_missed} days without the daily report.`;
}

/** The page as text, one line per stage. */
export function introductionLines(intro: Introduction): string[] {
	return intro.stages.map((s) => {
		const lacks = s.state === 'closed' && s.missing.length ? ` Its opening lacks: ${s.missing.join('; ')}.` : '';
		const free = mayOpen(s) ? ' It may be opened now.' : '';
		return `${s.text}${s.state === 'closed' ? lacks + free : ''}`;
	});
}

/** The introduction's page. */
export function introductionLink(): string {
	return '#/introduction';
}
