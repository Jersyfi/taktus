// The reports to the owner in the web app (UC-6.11, DEC-0218, ADR-0120): what a report's view
// holds as the surface sends it, and the few decisions the page makes about showing it — which
// reports are open, in which order, and the sentence that counts them. Nothing here reads or
// changes a report; the surface does.

/** One answer the report offers: an option of a decision request, or that it is done. */
export interface Offered {
	id: string;
	label: string;
	recommended?: boolean;
}

/** `GET /owner/reports/{id}`: the report's view, with its history (ADR-0045). The history
 * says whether the reader acted, never who did. */
export interface ReportView {
	id: string;
	kind: 'decision' | 'need' | 'date' | 'failure' | 'signals';
	title: string;
	needed: string[];
	steps: string[];
	standing_still: string[];
	due: string;
	offered: Offered[];
	links?: { label: string; url: string }[];
	raised_at: string;
	state: 'open' | 'reflected' | 'filed';
	reading?: { answer: string; kept: boolean; at: string; by_you: boolean } | null;
	filed?: { answer: string; at: string; record?: string | null; where?: string | null; by_you: boolean } | null;
	history?: { at: string; event: string; by_you: boolean }[];
}

/** `GET /owner/reports`. */
export interface ReportList {
	reports: ReportView[];
}

/** `POST /owner/reports/{id}/answer` and `…/confirm`: what became of the answer, the sentence
 * the channel would have said, and the view after it. */
export interface Answered {
	outcome: string;
	message: string;
	report: ReportView;
}

/** What each kind is called on the page: the words of the repository text. */
export const KIND: Record<ReportView['kind'], string> = {
	decision: 'Decision request',
	need: 'Needs request',
	date: 'Date',
	failure: 'Failure',
	signals: 'Daily signals'
};

/** Where the report stands, said to its reader. */
export function standing(report: ReportView): string {
	if (report.state === 'filed') return report.filed?.by_you ? 'answered by you, and filed' : 'answered, and filed';
	if (report.state === 'reflected')
		return report.reading?.by_you ? 'your answer was read back; it waits for your confirmation' : 'an answer waits for its confirmation';
	return 'open, waiting for an answer';
}

/** The reports not yet answered, newest first: the start page's list. */
export function openReports(reports: ReportView[]): ReportView[] {
	return reports
		.filter((r) => r.state !== 'filed')
		.sort((a, b) => (a.raised_at < b.raised_at ? 1 : a.raised_at > b.raised_at ? -1 : a.id.localeCompare(b.id)));
}

/** The sentence over the start page's list. */
export function openLine(count: number): string {
	if (count === 0) return 'No report waits for an answer.';
	return count === 1 ? '1 report waits for an answer.' : `${count} reports wait for an answer.`;
}

/** The label of the answer a reading or a filing names. */
export function answerLabel(report: ReportView, answer: string): string {
	return report.offered.find((o) => o.id === answer)?.label ?? answer;
}
