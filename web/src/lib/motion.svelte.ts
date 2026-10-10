// Whether motion is allowed (UC-6.10 *calm on request*).
//
// Motion is allowed unless the reader stopped it or the system asks for reduced motion. The
// system's setting is read before anything is drawn, so that it holds from the first moment.
// The glyph drawn is then the vocabulary's own `still` glyph: every motion replaced by its
// still mark, and nothing else changed (ADR-0059 §2).

import type { Drawn, Glyph } from './types';

function systemAsksForCalm(): boolean {
	try {
		return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
	} catch {
		return false;
	}
}

class Motion {
	stoppedByReader = $state(false);
	reducedBySystem = $state(systemAsksForCalm());

	get allowed(): boolean {
		return !this.stoppedByReader && !this.reducedBySystem;
	}

	listen(): () => void {
		if (typeof matchMedia !== 'function') return () => {};
		const query = matchMedia('(prefers-reduced-motion: reduce)');
		const changed = () => (this.reducedBySystem = query.matches);
		query.addEventListener('change', changed);
		return () => query.removeEventListener('change', changed);
	}
}

export const motion = new Motion();

/** The glyph to draw: with motion where it is allowed, the still one otherwise. */
export function chosen(drawn: Drawn, allowed: boolean): Glyph {
	return allowed ? drawn.moving : drawn.still;
}
