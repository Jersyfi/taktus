// End-to-end chains across domains, as the surface answers them (UC-15.4, ADR-0301 §4).
//
// `GET /chains` lists the declared chains with their latest run; `POST /chain-runs/{id}/decision`
// carries a person's decision on a halted chain (ADR-0302 §3). What is drawn here is read from
// the answer and computed nowhere else.

export const CHAINS = 'chains';

export interface HandoverItem {
	input: string;
	step: string;
	select?: string;
	clause: string;
}

export interface ChainLink {
	process_version: string;
	handover?: HandoverItem[];
}

export type ChainState = 'running' | 'waiting' | 'halted' | 'finished' | 'stopped';

export interface ChainRunView {
	id: string;
	state: ChainState;
	started_at: string;
	updated_at: string;
	link: number;
	runs: string[];
	handovers: string[];
	reason?: string | null;
	missing: string[];
	ended_at?: string | null;
	measured?: string | null;
}

export interface ChainView {
	id: string;
	name: string;
	links: ChainLink[];
	slo?: { latency?: string; completion?: number };
	escalation?: { role: string; react_within: string; path: string };
	declared_at: string;
	runs: ChainRunView[];
}

export interface ChainList {
	chains: ChainView[];
}

export function decisionPath(chainRun: string): string {
	return `chain-runs/${encodeURIComponent(chainRun)}/decision`;
}

/** Where a chain run stands, in one line: the link it stands at, and why where it is not
 * running or finished. */
export function standing(chain: ChainView, run: ChainRunView): string {
	const at = chain.links[run.link]?.process_version ?? `link ${run.link + 1}`;
	switch (run.state) {
		case 'finished':
			return `Finished: every link ran, ${run.handovers.length} handover(s) recorded.`;
		case 'running':
			return `Running at ${at}.`;
		case 'waiting':
			return `Waits at ${at}; it goes on by itself once that link finished.`;
		case 'halted':
			return `Halted after ${at}: the handover lacks ${run.missing.join(', ')}.`;
		case 'stopped':
			return `Stopped at ${at}.`;
	}
}

/** The chain's own objectives, in words; empty where it names none. */
export function objectives(chain: ChainView): string {
	const parts: string[] = [];
	if (chain.slo?.latency) parts.push(`a run within ${chain.slo.latency}`);
	if (chain.slo?.completion !== undefined) parts.push(`${Math.round(chain.slo.completion * 100)} % of runs finish`);
	return parts.join(', ');
}
