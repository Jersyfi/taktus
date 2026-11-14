// A change as one short line (ADR-0322 §4, *Just happened*): what happened to which run or step,
// from the fields the change carries and nothing else. No person is named: a change names a run,
// a step and a decision request, never who acted.

import type { Change } from './types';

const VERB: Record<string, string> = {
	'decision.answered': 'answered',
	'decision.applied': 'applied',
	'decision.confirmed': 'confirmed',
	'decision.raised': 'raised',
	'decision.reread': 'read back',
	'run.created': 'created',
	'run.escalated': 'escalated',
	'run.finished': 'finished',
	'run.halted': 'halted',
	'run.recovered': 'recovered',
	'run.resumed': 'resumed',
	'run.started': 'started',
	'run.waiting_human': 'waits for a person',
	'step.admitted': 'admitted',
	'step.adopted': 'adopted',
	'step.anchored': 'stopped at an anchor',
	'step.awaiting': 'awaits an answer',
	'step.confirmed': 'confirmed',
	'step.decided': 'decided',
	'step.declined': 'declined',
	'step.failed': 'failed',
	'step.finished': 'finished',
	'step.performed': 'performed',
	'step.rejected': 'rejected',
	'step.started': 'started',
	'step.taken_over': 'taken over',
	'step.takeover_lapsed': 'take-over lapsed',
	'step.waiting': 'waits'
};

/** The process a change is of, by its name without the version, where the change says it. */
export function processOf(change: Change): string | null {
	if (!change.process) return null;
	const at = change.process.lastIndexOf('@');
	return at > 0 ? change.process.slice(0, at) : change.process;
}

/** One line: "Step draft of run r1 finished", "Decision request q1 raised". */
export function changeLine(change: Change): string {
	const verb = VERB[change.kind] ?? change.kind;
	if (change.kind.startsWith('decision.') && change.decision_request) {
		return `Decision request ${change.decision_request} ${verb}`;
	}
	if (change.kind.startsWith('step.') && change.step) return `Step ${change.step} of run ${change.run} ${verb}`;
	return `Run ${change.run} ${verb}`;
}

/** The time of a change, as the reader's clock shows it: hours and minutes. */
export function changeTime(change: Change): string {
	const at = new Date(change.recorded_at);
	if (Number.isNaN(at.getTime())) return '';
	return at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
