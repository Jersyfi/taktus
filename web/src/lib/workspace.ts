// What the plan dialogue, the coach, the structure and the administration hand the web app
// (ADR-0279). The surface computes all of it; the pages draw it and send what a person chose.

export type Mode = 'guided' | 'expert';

export interface Question {
	field: string;
	asks: string;
	explains: string;
	step_id: string | null;
}

export interface Setting {
	field: string;
	value: string;
	why: string;
	asked: boolean;
}

export interface PlanDraftView {
	draft: {
		id: string;
		version: number;
		goal?: string;
		due?: string;
		autonomy_level?: number;
		autonomy_reason?: string;
		steps?: { id: string; method: string; reason: string }[];
		process_version?: string;
		commissioned_version?: number;
	};
	mode: Mode;
	plan_version: string;
	commissioned: boolean;
	missing: string[];
	unestimable: string[];
	estimates: string[];
	settings: Setting[];
	question: Question | null;
}

export interface Template {
	ref: string;
	name: string;
	level: number;
	steps: string[];
}

export interface CoachHint {
	id: string;
	says: string;
	procedure: string;
	offered_at: string;
}

export interface CoachState {
	settings: { on: boolean; hints_per_week: number; default_hints_per_week: number };
	hints: CoachHint[];
	share: { lasted: number; checked: number };
}

export interface Unit {
	id: string;
	name: string;
	level: number;
	parent?: string;
	private?: boolean;
	owner?: string;
	circle?: 'alone' | 'team' | 'project_team' | 'company';
	references?: { kind: string; link: string; title?: string }[];
}

export interface Structure {
	levels: string[];
	units: Unit[];
	placements: { kind: string; object: string; unit: string }[];
	yours: string[];
}

export interface Statement {
	text: string;
	source?: { title: string; link: string };
}

export interface Turn {
	at: string;
	channel: string;
	speaker: 'participant' | 'taktus';
	text?: string;
	statements?: Statement[];
}

export interface Session {
	id: string;
	project: string;
	turns?: Turn[];
	outcomes?: { kind: string; ref: string; summary: string }[];
}

/** The level of a unit, in the words the organisation named its levels. */
export function levelName(structure: Structure, unit: Unit): string {
	return structure.levels[unit.level] ?? `level ${unit.level}`;
}

/** The units in the order of a tree: each followed by the units below it. */
export function tree(units: Unit[]): { unit: Unit; depth: number }[] {
	const below = new Map<string | undefined, Unit[]>();
	for (const u of units) below.set(u.parent, [...(below.get(u.parent) ?? []), u]);
	const ids = new Set(units.map((u) => u.id));
	const roots = units.filter((u) => !u.parent || !ids.has(u.parent));
	const out: { unit: Unit; depth: number }[] = [];
	const walk = (u: Unit, depth: number) => {
		out.push({ unit: u, depth });
		for (const child of below.get(u.id) ?? []) walk(child, depth + 1);
	};
	for (const r of roots) walk(r, 0);
	return out;
}

/** What a guided answer in a text box becomes for the field the question asks. */
export function answerValue(question: Question, typed: string): unknown {
	if (question.field === 'autonomy_level') return Number(typed);
	if (question.field === 'estimates') {
		const figure = Number(typed.split(/\s+/)[0]);
		const basis = typed.replace(/^\S+\s*/, '').trim();
		return { figure, unit: 'seconds', ...(basis ? { basis } : {}) };
	}
	if (question.field === 'steps') return { process_version: typed };
	return typed;
}
