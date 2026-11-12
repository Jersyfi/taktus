// Data-protection requests and the processing evidence, as the HTTP surface answers them
// (ADR-0176, UC-11.2): `GET`/`POST /subjects/requests`, `…/{id}/confirm`, `…/{id}/withdraw` and
// `GET /evidence`. A request is prepared by anyone the surface admits and carried out by a person
// who states that they checked the requester's identity; the page says back what will happen
// before it sends the confirmation.

export type RequestKind = 'access' | 'rectification' | 'erasure' | 'portability';
export type RequestState = 'prepared' | 'carried_out' | 'withdrawn';

export const KINDS: RequestKind[] = ['access', 'rectification', 'erasure', 'portability'];

/** One line of `GET /subjects/requests`. */
export interface RequestLine {
	id: string;
	kind: RequestKind;
	state: RequestState;
	created_at: string;
	prepared_by: string;
	carried_out_by: string | null;
	withdrawn_by: string | null;
}

/** The count `taktusctl subject show` prints beside a request. */
export interface Holds {
	runs: number;
	objects: number;
	kept: number;
	in_flight: string[];
}

/** One request with its holdings, as prepared, shown or carried out. */
export interface SubjectRequest extends RequestLine {
	subject: string;
	holds: Holds;
	holdings: unknown[];
	outcome?: unknown;
	export?: unknown;
}

export const subjectsLink = '#/subjects';
export const subjectsPath = 'subjects/requests';

const KIND_WORDS: Record<RequestKind, string> = {
	access: 'an export of what Taktus holds of the subject, with how it was processed',
	portability: 'an export of what Taktus holds of the subject, in a form another system reads',
	erasure: "the erasure of the subject's run content, the ledger and provenance chains verified after it",
	rectification: 'a record that you corrected the data at its source'
};

/** What a confirmation will do, said back before it is sent (ADR-0008). */
export function sayBack(request: SubjectRequest): string {
	const runs = request.holds.runs === 1 ? '1 run' : `${request.holds.runs} runs`;
	const kept = request.holds.kept ? `; ${request.holds.kept} shared objects stay, another run still needs them` : '';
	const pending = request.holds.in_flight.length
		? ` ${request.holds.in_flight.length === 1 ? 'One run is' : `${request.holds.in_flight.length} runs are`} still in flight and are left as they are.`
		: '';
	const final = request.kind === 'erasure' ? ' It cannot be undone.' : '';
	return `You confirm that you checked who asked. Taktus carries out ${KIND_WORDS[request.kind]}, over ${runs}${kept}.${pending}${final}`;
}

/** Why a request cannot be confirmed now, or null when it can. */
export function notConfirmable(request: SubjectRequest): string | null {
	if (request.state !== 'prepared') return `This request is ${request.state.replace('_', ' ')}.`;
	return null;
}

/** An export as a file the person saves; Taktus keeps no copy. */
export function exportFile(request: SubjectRequest): { name: string; text: string } | null {
	if (request.export === undefined) return null;
	return { name: `${request.id}-${request.kind}.json`, text: JSON.stringify(request.export, null, 2) };
}

/** `GET /evidence` (ADR-0176 §8): generated from configuration and the ledger. */
export interface ProcessingEvidence {
	tenant: string;
	generated_at: string;
	legally_reviewed: false;
	notice: string;
	residency_rule: string;
	personal_capabilities: string[];
	personal_data_steps: {
		process: string;
		version: string;
		step: string;
		serves: string;
		personal_data: string;
		adapter: string;
		location: string;
		within_residency_rule: boolean | null;
	}[];
	adapters: { adapter: string; kind: string; serves: string[]; location: string; within_residency_rule: boolean | null }[];
	keeping: { record: string; holds: string; kept: string }[];
	requests: Record<'prepared' | 'erased' | 'exported' | 'rectified' | 'withdrawn', number>;
}

/** The evidence's one-sentence summary, which never claims compliance. */
export function evidenceSentence(evidence: ProcessingEvidence): string {
	const steps = evidence.personal_data_steps.length;
	const outside = evidence.personal_data_steps.filter((s) => s.within_residency_rule === false).length;
	const where = outside ? `, ${outside} of them outside the residency rule` : '';
	return `${steps} ${steps === 1 ? 'step processes' : 'steps process'} personal data${where}. Not legally reviewed.`;
}
