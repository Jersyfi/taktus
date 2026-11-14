// Picture first, text on a switch (ADR-0322 §2). The default for every page is kept by the device;
// a page's own choice holds while the page is open. Where the system asks for forced colours, the
// default is the text. The storage can be refused or empty; the page is right without it.

export type Display = 'picture' | 'text';
const KEY = 'taktus.display';

function forcedColours(): boolean {
	try {
		return typeof matchMedia === 'function' && matchMedia('(forced-colors: active)').matches;
	} catch {
		return false;
	}
}

/** The default as stored, or as the system suggests where nothing is stored. */
export function storedDisplay(storage: Pick<Storage, 'getItem'> | null = safeStorage(), forced = forcedColours()): Display {
	try {
		const found = storage?.getItem(KEY) ?? null;
		if (found === 'picture' || found === 'text') return found;
	} catch {
		// Refused: the system's suggestion holds.
	}
	return forced ? 'text' : 'picture';
}

function safeStorage(): Storage | null {
	try {
		return typeof localStorage === 'undefined' ? null : localStorage;
	} catch {
		return null;
	}
}

class DisplayChoice {
	/** The default for every page. */
	fallback: Display = $state(storedDisplay());
	/** A page's own choice, while it is open: keyed by the page. */
	private chosen: Record<string, Display> = $state({});

	of(page: string): Display {
		return this.chosen[page] ?? this.fallback;
	}

	choose(page: string, display: Display): void {
		this.chosen = { ...this.chosen, [page]: display };
	}

	/** Leaving a page returns it to the default. */
	forget(page: string): void {
		const { [page]: _, ...rest } = this.chosen;
		this.chosen = rest;
	}

	setDefault(display: Display): void {
		this.fallback = display;
		this.chosen = {};
		try {
			safeStorage()?.setItem(KEY, display);
		} catch {
			// Kept for this visit only.
		}
	}
}

export const display = new DisplayChoice();
