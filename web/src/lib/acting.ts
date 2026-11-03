// What acts for the tenant, what depends on it, and how a process really runs, as the surface
// answers it (ADR-0147, DEC-0218): `GET /register` and its inventory, the stop of an adapter,
// `GET /dependencies/…`, and `GET /processes/{id}/variants`. The pages show what they are
// handed; nothing here computes a figure, and nothing names a person (principle 14).

import { read, send, type Answer } from './api';

// --- the shapes the surface answers --------------------------------------------------------------

export interface RemovalSeen {
	verdict: 'broke' | 'changed' | 'untested' | 'exception';
	tested_at: string;
	reason?: string;
}

export interface Used {
	days: number;
	steps: number;
	runs: number;
	tokens: number;
	compute_seconds: number;
	money: Record<string, number>;
}

/** One step an adapter serves, and what it comes to without it. */
export interface ActorUse {
	process_id: string;
	version: string;
	step_id: string;
	served: string;
	level: number;
	exactness?: string;
	without: 'breaks' | 'degrades';
	instead?: string;
	/** The role that takes the step over where it falls back to a person (ADR-0146). */
	role?: string;
	reason: string;
}

export interface RegisterRow {
	adapter: string;
	family: string;
	serves: string[];
	maturity?: string;
	missing: string[];
	removal?: RemovalSeen;
	level?: number;
	exactness?: string;
	location?: string;
	residency: 'inside' | 'outside' | 'undeclared';
	processes: string[];
	uses: ActorUse[];
	used: Used;
	stopped: boolean;
	attention: string[];
	text: string;
}

export interface Register {
	tenant: string;
	permitted: string;
	rows: RegisterRow[];
	summary: string;
}

export interface RemoveView {
	adapter: string;
	configured: boolean;
	breaks: ActorUse[];
	degrades: ActorUse[];
	removal?: RemovalSeen;
	summary: string;
}

export interface Reached {
	run_id: string;
	step_id: string;
	process_version: string;
	exactness?: string;
	recorded_at: string;
	left: string[];
}

export interface WrongResultView {
	run_id: string;
	step_id: string;
	process_version?: string;
	exactness?: string;
	left_itself: string[];
	reached: Reached[];
	affected: number;
	built_on: Record<string, number>;
	left: number;
	since_when: string;
	summary: string;
}

export interface ResidencyView {
	permitted: string;
	rows: { adapter: string; family: string; location?: string; residency: string; processes: string[] }[];
	summary: string;
}

export interface Variant {
	path: string[];
	end: string;
	runs: number;
	share: number;
	examples: string[];
	designed: boolean;
	text: string;
}

export interface StepWaiting {
	step_id: string;
	seconds: number;
	by_cause: Record<string, number>;
	share: number | null;
}

export interface VariantsView {
	process_id: string;
	version?: string;
	designed: string[];
	runs: number;
	in_flight: number;
	on_designed_path: number | null;
	variants: Variant[];
	waiting: StepWaiting[];
	/** A role's waiting, null where fewer than two hold the role (ADR-0015). */
	roles: { role: string; seconds: number | null; text: string }[];
	proposals: { kind: string; step_id: string; evidence: string; text: string }[];
	summary: string;
}

// --- reads and the one act -----------------------------------------------------------------------

export const REGISTER = 'register';
export const INVENTORY = 'register/inventory';
export const RESIDENCY = 'dependencies/residency';

export function removePath(adapter: string): string {
	return `dependencies/remove/${encodeURIComponent(adapter)}`;
}

export function wrongResultPath(runId: string, stepId: string): string {
	return `dependencies/wrong-result/${encodeURIComponent(runId)}/${encodeURIComponent(stepId)}`;
}

export function variantsPath(processId: string): string {
	return `processes/${encodeURIComponent(processId)}/variants`;
}

/** ADR-0138's stop of the adapter, by the signed-in person; it asks for no reason. */
export function stopAdapter(base: URL, adapter: string, fetcher: typeof fetch = fetch): Promise<Answer<unknown>> {
	return send<unknown>(base, `register/${encodeURIComponent(adapter)}/stop`, {}, fetcher);
}

export function readRegister(base: URL, fetcher: typeof fetch = fetch): Promise<Answer<Register>> {
	return read<Register>(base, REGISTER, fetcher);
}

// --- what the pages say in words -----------------------------------------------------------------

export function percent(share: number): string {
	return `${Math.round(share * 100)} %`;
}

export function hours(seconds: number): string {
	return seconds >= 3600 ? `${(seconds / 3600).toFixed(1)} h` : `${Math.round(seconds / 60)} min`;
}

/** What an adapter used, in one line: steps, runs, and the quantities it recorded. */
export function usedText(used: Used): string {
	const parts = [`${used.steps} steps in ${used.runs} runs`];
	if (used.tokens) parts.push(`${used.tokens.toLocaleString('en')} tokens`);
	if (used.compute_seconds) parts.push(`${hours(used.compute_seconds)} compute`);
	for (const [currency, amount] of Object.entries(used.money)) parts.push(`${amount.toFixed(2)} ${currency.toUpperCase()}`);
	return `${parts.join(' · ')} over ${used.days} days`;
}

/** A variant's path, step by step, as the page draws it: each deviation names its step. */
export function deviations(variant: Variant): { what: string; step: string }[] {
	return variant.path.map((item) => {
		const [what, step] = item.split('@');
		return { what: what ?? item, step: step ?? '' };
	});
}

/** The start page's line for the register: how many adapters need attention (ADR-0147). */
export function registerLine(register: Register): string {
	const needing = register.rows.filter((r) => r.attention.length).length;
	return needing ? `${needing} of ${register.rows.length} adapters need attention.` : register.summary;
}
