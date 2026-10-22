// The reader's sign-in (ADR-0119).
//
// The reader gives their account key once. The web app sends it to the instance in
// `Authorization: Bearer`, in exchange for a session cookie, and forgets it. The cookie is
// `HttpOnly`: no script of the page can read it. The browser sends it with every request to the
// instance, in every tab, until it expires or the reader signs out. The key is never kept in
// storage and never put in an address.

import type { Problem } from './types';

/** Where an earlier version of the web app kept the key for one tab (ADR-0063). */
const OLD_KEY = 'taktus.key';

export type SignedIn = { ok: true; identity: string; expiresAt: string } | { ok: false; problem: Problem };

/** Exchanges the key for the session cookie. The key leaves the page in the header only. */
export async function signIn(base: URL, key: string, fetcher: typeof fetch = fetch): Promise<SignedIn> {
	const response = await fetcher(new URL('session', base), {
		method: 'POST',
		credentials: 'same-origin',
		headers: { Authorization: `Bearer ${key.trim()}`, Accept: 'application/json' }
	});
	if (response.ok) {
		const body = (await response.json()) as { identity: string; expires_at: string };
		return { ok: true, identity: body.identity, expiresAt: body.expires_at };
	}
	return { ok: false, problem: { status: response.status, title: response.statusText, detail: '' } };
}

/** Ends the session; the instance clears the cookie. */
export async function signOut(base: URL, fetcher: typeof fetch = fetch): Promise<void> {
	await fetcher(new URL('session', base), { method: 'DELETE', credentials: 'same-origin' });
}

/** Removes a key an earlier version kept in the tab's storage, so that none outlives it. */
export function forgetOldKey(storage: Storage | null = tabStorage()): void {
	try {
		storage?.removeItem(OLD_KEY);
	} catch {
		// Storage that refuses holds nothing.
	}
}

function tabStorage(): Storage | null {
	try {
		return typeof sessionStorage === 'undefined' ? null : sessionStorage;
	} catch {
		return null;
	}
}
