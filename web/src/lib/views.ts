// What a person may ask Taktus for, and the organisation seen as value streams, as the surface
// answers them (ADR-0159): `GET /catalogue`, the start of an entry, `GET /streams` and
// `GET /streams/{stream}`. The pages draw what they are handed; nothing here computes a figure,
// and nothing names a person (principle 14).

import { send, type Answer } from './api';

// --- the catalogue (UC-1.13) ---------------------------------------------------------------------

export interface CatalogueInput {
	name: string;
	description: string;
	required: boolean;
	example?: unknown;
}

export interface CatalogueEntry {
	process: string;
	name: string;
	description?: string;
	version: string;
	level: number;
	needs: CatalogueInput[];
	roles: string[];
	/** The one start command every channel issues. */
	command: { intent: string; recognised: string };
	start: {
		web: string;
		agent: { tool: string; arguments: Record<string, unknown>; right: string; held: boolean };
		chat?: string;
	};
	text: string;
}

export interface Catalogue {
	entries: CatalogueEntry[];
	summary: string;
	nothing_fits: string;
}

export interface Started {
	run_id: string;
	process_version: string;
	state: string;
}

export const CATALOGUE = 'catalogue';

/** The entry started as the signed-in person: the one start command on `channel.web`. */
export function startEntry(
	base: URL,
	process: string,
	inputs: Record<string, unknown>,
	fetcher: typeof fetch = fetch
): Promise<Answer<Started>> {
	return send<Started>(base, `catalogue/${encodeURIComponent(process)}/start`, { inputs }, fetcher);
}

/** The inputs as the form holds them, each a text, given to the start as written; an empty
 * optional input is left out. */
export function inputsOf(entry: CatalogueEntry, form: Record<string, string>): Record<string, unknown> {
	const given: Record<string, unknown> = {};
	for (const input of entry.needs) {
		const value = (form[input.name] ?? '').trim();
		if (value || input.required) given[input.name] = value;
	}
	return given;
}

// --- the value streams (UC-15.6) -----------------------------------------------------------------

export interface Crossing {
	from_process: string;
	from_step: string;
	from_role: string;
	from_units: string[];
	to_process: string;
	to_step: string;
	to_role: string;
	to_units: string[];
	text: string;
}

export interface StreamFigures {
	steps: number;
	autonomy: Record<string, number>;
	methods: Record<string, number>;
	reproducible: number | null;
	runs: number;
	flow_efficiency: number | null;
	blocked_share: number | null;
	top_cause?: string;
	crossings: Crossing[];
}

export interface StreamCard {
	stream: string;
	revision: number;
	name: string;
	kind: 'core' | 'management' | 'support';
	trigger: string;
	outcome: string;
	role: string;
	processes: string[];
	figures: StreamFigures;
	text: string;
}

export interface StreamMap {
	days: number;
	management: StreamCard[];
	core: StreamCard[];
	support: StreamCard[];
	outside: { process: string; name: string }[];
	summary: string;
}

export interface Lane {
	key: string;
	kind: 'reproducible' | 'variable' | 'role';
	title: string;
	role?: string;
	units: string[];
	waiting_seconds?: number;
	text: string;
}

export interface Chip {
	process: string;
	step: string;
	method: string;
	exactness?: string;
	lane: string;
	fallback_lane?: string;
	text: string;
}

export interface StreamLanes {
	card: StreamCard;
	columns: { process: string; name: string; version?: string; level?: number }[];
	lanes: Lane[];
	chips: Chip[];
	units: string[];
	summary: string;
}

export const STREAMS = 'streams';

export function streamPath(stream: string): string {
	return `streams/${encodeURIComponent(stream)}`;
}

export function streamLink(stream: string): string {
	return `#/streams/${encodeURIComponent(stream)}`;
}

/** The method kinds in the order a mix bar draws them: reproducible first, then variable, then
 * a person and a wait (methods.md). */
export const METHOD_ORDER = ['rule', 'statistics', 'ml', 'neural', 'wait', 'llm', 'worker', 'human'] as const;

/** A share map as the segments of a bar, in a fixed order, leaving out what is not there. */
export function segments(shares: Record<string, number>, order: readonly string[]): { key: string; share: number }[] {
	const known = order.filter((k) => (shares[k] ?? 0) > 0).map((k) => ({ key: k, share: shares[k]! }));
	const rest = Object.keys(shares)
		.filter((k) => !order.includes(k) && shares[k]! > 0)
		.sort()
		.map((k) => ({ key: k, share: shares[k]! }));
	return [...known, ...rest];
}

/** The swimlanes as a grid: for each lane, the chips of each column, in the order of the
 * stream. A cell may hold none. */
export function grid(view: StreamLanes): { lane: Lane; cells: Chip[][] }[] {
	return view.lanes.map((lane) => ({
		lane,
		cells: view.columns.map((column) => view.chips.filter((c) => c.lane === lane.key && c.process === column.process))
	}));
}

/** The chips of a column that fall back to a lane's role: drawn as a dashed mark in that lane. */
export function fallbacks(view: StreamLanes, lane: Lane, process: string): Chip[] {
	return view.chips.filter((c) => c.fallback_lane === lane.key && c.process === process);
}
