// Processes nobody wrote down, brought to light (UC-9.4, ADR-0245 §2), as the surface answers
// them: `GET /discoveries`, `POST /discoveries`, the interview (`GET`/`POST
// /discoveries/interview`), a record's next stage (`POST /discoveries/{id}/stages/{stage}`) and
// a pattern's agreement (`POST /discoveries/{id}/agree`). The surface decides whether a stage
// may follow; the page only offers the next one and says what the surface refused. The decision
// to automate is a person's. A pattern found for the reader is theirs alone until they agree:
// the page never shows whose it is (principle 14).

export const STAGES = ['visible', 'documented', 'valued', 'decided', 'automated'] as const;
export type Stage = (typeof STAGES)[number];
export type Origin = 'interview' | 'pattern' | 'request';

export interface Discovered {
	id: string;
	title: string;
	origin: Origin;
	found: string;
	stage: Stage;
	/** Set only on a pattern found for the reader, until they agree. Never shown. */
	reader?: string | null;
	description?: string | null;
	owner_role?: string | null;
	minutes_by_hand?: number | null;
	cases_per_month?: number | null;
	decision?: 'automate' | 'keep' | null;
	process_id?: string | null;
	at: string;
}

/** `GET /discoveries`. */
export interface Discoveries {
	discoveries: Discovered[];
}

export type Mode = 'guided' | 'expert';

export interface Question {
	key: string;
	question: string;
	example?: string;
}

/** `GET /discoveries/interview?mode=`. */
export interface Interview {
	mode: Mode;
	questions: Question[];
}

/** `POST /discoveries/interview`. */
export interface Interviewed {
	description: string;
	owner_role: string;
}

/** The stage after a record's own, or none when it is automated. */
export function nextStage(stage: Stage): Exclude<Stage, 'visible'> | null {
	const at = STAGES.indexOf(stage);
	return at < 0 || at + 1 >= STAGES.length ? null : (STAGES[at + 1] as Exclude<Stage, 'visible'>);
}

/** Whether a record is a pattern found for the reader that waits for their agreement. */
export function mine(d: Discovered): boolean {
	return d.origin === 'pattern' && !!d.reader;
}

/** What each stage asks for, as the surface takes it. */
export interface Field {
	key: string;
	label: string;
	kind: 'text' | 'long' | 'number' | 'choice';
	choices?: string[];
}

export const STAGE_FIELDS: Record<Exclude<Stage, 'visible'>, Field[]> = {
	documented: [
		{ key: 'description', label: 'What is done, when, with what, and when it is done', kind: 'long' },
		{ key: 'owner_role', label: 'The role responsible for it', kind: 'text' }
	],
	valued: [
		{ key: 'minutes_by_hand', label: 'Minutes a case takes by hand', kind: 'number' },
		{ key: 'cases_per_month', label: 'Cases a month', kind: 'number' }
	],
	decided: [{ key: 'decision', label: 'Your decision', kind: 'choice', choices: ['automate', 'keep'] }],
	automated: [
		{ key: 'process_id', label: 'The process it runs as', kind: 'text' },
		{ key: 'level', label: 'The level it enters at', kind: 'choice', choices: ['1', '2'] },
		{ key: 'instructions', label: 'Its takeover instructions', kind: 'long' }
	]
};

/** The body of a stage, from what the person typed: numbers as numbers, the level as one. */
export function stageBody(stage: Exclude<Stage, 'visible'>, values: Record<string, string>): Record<string, unknown> {
	const body: Record<string, unknown> = {};
	for (const f of STAGE_FIELDS[stage]) {
		const v = (values[f.key] ?? '').trim();
		if (!v) continue;
		body[f.key] = f.kind === 'number' || f.key === 'level' ? Number(v) : v;
	}
	return body;
}

const ORIGINS: Record<Origin, string> = {
	interview: 'from an interview',
	pattern: 'a pattern in your own requests',
	request: 'from a request'
};

/** One record in words. */
export function discoveredLine(d: Discovered): string {
	return `${d.title}, ${ORIGINS[d.origin] ?? d.origin}: ${d.stage}.`;
}
