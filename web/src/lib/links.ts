// Where each level lives in the web app. The route is the part of the address after `#`
// (ADR-0063), so every link starts with `#/`.

/** A run's level. */
export function runLink(runId: string): string {
	return `#/runs/${encodeURIComponent(runId)}`;
}

/** A process's level, for `process@version` or a bare process id (the active version). */
export function processLink(ref: string): string {
	const at = ref.lastIndexOf('@');
	if (at <= 0) return `#/processes/${encodeURIComponent(ref)}`;
	return `#/processes/${encodeURIComponent(ref.slice(0, at))}/${encodeURIComponent(ref.slice(at + 1))}`;
}

/** The origin of a step's result. */
export function originLink(runId: string, stepId: string): string {
	return `#/origins/${encodeURIComponent(runId)}/${encodeURIComponent(stepId)}`;
}

/** The decision requests addressed to the reader, or one of them. */
export function requestsLink(requestId?: string): string {
	return requestId ? `#/requests/${encodeURIComponent(requestId)}` : '#/requests';
}

/** Where a process is changed in dialogue, and rolled back (ADR-0091 §6). */
export function changeLink(processId: string): string {
	return `#/changes/${encodeURIComponent(processId)}`;
}

/** A report to the owner: where every link a channel carries to it leads (ADR-0120). The
 * control plane builds the same route (`rendering.py`'s `view_url`). */
export function reportLink(reportId: string): string {
	return `#/reports/${encodeURIComponent(reportId)}`;
}

/** A run opened at the trace inside one of its steps: the route a share's link names
 * (ADR-0135). The control plane builds the same route (`traces.py`'s `link`). */
export function traceLink(runId: string, stepId: string): string {
	return `#/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}`;
}
