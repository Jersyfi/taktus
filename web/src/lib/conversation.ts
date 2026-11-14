// A person's conversation with Taktus, as the page "Ask Taktus" reads it (ADR-0325, UC-1.14).
// `GET /conversation` gives the turns and the acts; `POST /conversation` says something;
// `POST /conversation/acts/{act}` answers an act with yes or no. The page computes nothing but
// where a link leads and whether to ask again.

import { changeLink, processLink, runLink } from './links';

export type Turn = {
	at: string;
	channel: string;
	speaker: 'person' | 'taktus';
	text: string;
	act?: string | null;
	run?: string | null;
};

export type ProposedAct = {
	id: string;
	act: string;
	arguments: Record<string, unknown>;
	read_back: string;
	channel: string;
	asked_at: string;
	state: 'waiting' | 'done' | 'declined' | 'failed';
	outcome?: string | null;
	links: Record<string, string>;
};

export type ConversationView = {
	available: boolean;
	conversation: string;
	turns: Turn[];
	acts: ProposedAct[];
	thinking: string | null;
	acts_offered: Record<string, string>;
};

export type Link = { label: string; href: string };

/** Where each thing an act created is seen: a run, a plan draft, a process and its proposals. */
export function linksOf(act: ProposedAct): Link[] {
	const links: Link[] = [];
	const made = act.links;
	if (made.run) links.push({ label: `Run ${made.run}`, href: runLink(made.run) });
	if (made.draft) links.push({ label: `Plan draft ${made.draft}`, href: '#/plans' });
	if (made.process) {
		if (made.version) links.push({ label: `${made.process} @ ${made.version}`, href: processLink(`${made.process}@${made.version}`) });
		else links.push({ label: `Proposals of ${made.process}`, href: changeLink(made.process) });
	}
	return links;
}

/** The act a turn of Taktus's proposed, if any. */
export function actOf(view: ConversationView, turn: Turn): ProposedAct | undefined {
	return turn.act ? view.acts.find((a) => a.id === turn.act) : undefined;
}

/** Whether the page asks for the conversation again: while a run forms an answer. */
export function waitingForAnswer(view: ConversationView | null): boolean {
	return view !== null && view.thinking !== null;
}

/** How long the page waits before it asks again, in milliseconds: soon at first, then less
 * often, never more often than once a second. */
export function nextAsk(asked: number): number {
	return Math.min(1000 * 2 ** Math.min(asked, 3), 8000);
}
