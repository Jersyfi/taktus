// A message to a running worker step, from the run's page (ADR-0156 §7). The page decides
// nothing: the surface refuses a step whose worker takes no message, or one that no longer runs,
// and says why; the page shows that reason. The text is read back before it is sent (ADR-0008).

import { send } from './api';
import type { RunLevel, StepElement } from './types';

/** The steps a message can be sent to: running worker steps of a running run, while no step of
 * the run is taken over by a person. */
export function steerable(level: RunLevel): StepElement[] {
	if (level.run.state !== 'running') return [];
	if (level.steps.some((s) => s.takeover?.standing === 'held')) return [];
	return level.steps.filter((s) => s.method === 'worker' && s.state === 'running');
}

/** The text as it will be sent, or null when there is none to send. */
export function readMessage(written: string): string | null {
	const text = written.trim();
	return text && text.length <= 8000 ? text : null;
}

/** Sends a message to a running step: `POST /runs/{id}/steps/{step}/messages`. */
export function sendMessage(base: URL, run: string, step: string, text: string, fetcher: typeof fetch = fetch) {
	return send<{ message: string; step_id: string; state: string }>(
		base,
		`runs/${encodeURIComponent(run)}/steps/${encodeURIComponent(step)}/messages`,
		{ text },
		fetcher
	);
}

/** What the page says once the surface answered, by its answer. */
export function messageSaid(ok: boolean, step: string, detail: string): string {
	if (ok) return `Sent to ${step}. Its worker receives it at its next boundary; the steps after that take it as an input.`;
	return `Not sent: ${detail || 'the step takes no message now'}.`;
}
