// The reader's account key, held for the browser tab's session only (ADR-0063).
//
// The key is kept in the tab's session storage: it ends when the tab closes, and no other tab
// or later visit reads it. It is never put in an address. Storage that refuses — a private
// window, a blocked site — leaves the key in memory for as long as the page lives.

const NAME = 'taktus.key';
let held: string | null = null;

function storage(): Storage | null {
	try {
		return typeof sessionStorage === 'undefined' ? null : sessionStorage;
	} catch {
		return null;
	}
}

export function currentKey(): string | null {
	if (held !== null) return held;
	try {
		held = storage()?.getItem(NAME) ?? null;
	} catch {
		held = null;
	}
	return held;
}

export function keepKey(key: string): void {
	held = key.trim() || null;
	try {
		if (held === null) storage()?.removeItem(NAME);
		else storage()?.setItem(NAME, held);
	} catch {
		// Kept in memory only.
	}
}

export function forgetKey(): void {
	keepKey('');
}
