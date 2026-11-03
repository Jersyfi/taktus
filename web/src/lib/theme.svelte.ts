// The theme the reader chose — System, Light or Dark — kept by the device, never by the account
// (ADR-0177 §3). *System* sets no attribute, and the stylesheet follows `prefers-color-scheme`.
// The storage can be refused or empty; the page is right without it.

export type ThemeChoice = 'system' | 'light' | 'dark';
export const THEMES: { id: ThemeChoice; label: string }[] = [
	{ id: 'system', label: 'System' },
	{ id: 'light', label: 'Light' },
	{ id: 'dark', label: 'Dark' }
];
const KEY = 'taktus.theme';

function stored(): ThemeChoice {
	try {
		const found = typeof localStorage === 'undefined' ? null : localStorage.getItem(KEY);
		return found === 'light' || found === 'dark' ? found : 'system';
	} catch {
		return 'system';
	}
}

/** Sets the document's attribute for a choice; `system` removes it. */
export function apply(choice: ThemeChoice, root: { dataset: DOMStringMap } | null = globalThis.document?.documentElement ?? null): void {
	if (!root) return;
	if (choice === 'system') delete root.dataset.theme;
	else root.dataset.theme = choice;
}

class Theme {
	choice: ThemeChoice = $state(stored());

	choose(choice: ThemeChoice): void {
		this.choice = choice;
		apply(choice);
		try {
			if (choice === 'system') localStorage.removeItem(KEY);
			else localStorage.setItem(KEY, choice);
		} catch {
			// Kept for this page only.
		}
	}
}

export const theme = new Theme();
