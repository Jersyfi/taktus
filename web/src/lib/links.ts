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
