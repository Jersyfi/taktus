// A page the surface refused: it keeps its name, and the surface's sentence is its heading.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import Unavailable from './Unavailable.svelte';

describe('a page the surface refused', () => {
	it('names the page and says why as a sentence', () => {
		const { body } = render(Unavailable, {
			props: { eyebrow: 'Needs', problem: 'only the owner, and the people the owner named, read the reports' }
		});
		expect(body).toContain('Needs');
		expect(body).toContain('Only the owner, and the people the owner named, read the reports.');
	});

	it('keeps a sentence that already ends', () => {
		const { body } = render(Unavailable, { props: { eyebrow: 'Introduction', problem: 'No stages (`taktusctl stage declare`)' } });
		expect(body).toContain('No stages (`taktusctl stage declare`)<');
	});
});
