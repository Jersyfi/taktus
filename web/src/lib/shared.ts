// Reads the frame and a page both need, made once (ADR-0323 §4). The frame reads the lines that
// set its marks and Today shows the same lines: without sharing, opening Today read
// `GET /owner/reports` three times and `GET /operation`, `/decisions`, `/autonomy` and
// `/findings` twice each. A read in flight is joined; an answer is kept for a short while and
// dropped when a change makes it old.

import { failed, read, type Answer } from './api';

const KEPT_MS = 15_000;

interface Kept {
	at: number;
	answer: Promise<Answer<unknown>>;
}

/** Kept per fetcher, so that a test's own fetcher never meets another's answers. */
let kept = new WeakMap<typeof fetch, Map<string, Kept>>();

/** A read of `path`, shared with every other caller within the window. A refusal is kept like an
 * answer; a failure is not: the next caller reads again. */
export function readShared<T>(
	base: URL,
	path: string,
	fetcher: typeof fetch = fetch,
	now: () => number = Date.now
): Promise<Answer<T>> {
	const key = new URL(path, base).href;
	let mine = kept.get(fetcher);
	if (!mine) kept.set(fetcher, (mine = new Map()));
	const store = mine;
	const found = store.get(key);
	if (found && now() - found.at < KEPT_MS) return found.answer as Promise<Answer<T>>;
	const answer = read<T>(base, path, fetcher);
	store.set(key, { at: now(), answer });
	void answer.then((a) => {
		if (!a.ok && failed(a.problem) && store.get(key)?.answer === answer) store.delete(key);
	});
	return answer;
}

/** Drops what was kept: a change arrived, or the reader signed in or out. */
export function forgetShared(): void {
	kept = new WeakMap();
}
