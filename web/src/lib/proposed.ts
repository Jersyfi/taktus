// The processes Taktus proposes, as `GET /process-proposals` hands them to the web app
// (UC-4.4, ADR-0270). The page computes nothing: the order and its reason are the surface's.

export interface ProcessProposal {
	id: string;
	kind: 'by_hand' | 'healed';
	process_id: string;
	takes_over: string;
	cost: string;
	why_now: string;
	order: string;
	/** Drawn from runs the reader started: shown to the reader alone. */
	yours: boolean;
}

export interface ProcessProposals {
	order: string;
	proposals: ProcessProposal[];
}

export interface Decided {
	proposal: ProcessProposal;
	/** The run that builds an accepted proposal; absent for a declined one. */
	run_id?: string;
}

/** The path of an act on one proposal. */
export function act(id: string, what: 'accept' | 'decline'): string {
	return `process-proposals/${encodeURIComponent(id)}/${what}`;
}
