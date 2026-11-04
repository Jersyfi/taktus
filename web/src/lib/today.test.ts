// The start page's area heading: the tenant's name where the surface hands one, its identifier
// only as a detail, and never the raw identifier as the heading.

import { describe, expect, it } from 'vitest';
import { areaTitle } from './today';

describe('the area heading', () => {
	it('heads an area by its name and keeps the identifier as a detail', () => {
		expect(areaTitle({ id: 'tnt_4f2a', name: 'Bakery' })).toEqual({ title: 'Bakery', detail: 'tnt_4f2a' });
	});
	it('never heads an area by its raw identifier', () => {
		const headed = areaTitle({ id: 'tnt_4f2a', name: 'tnt_4f2a' });
		expect(headed.title).not.toContain('tnt_');
		expect(headed.detail).toBe('tnt_4f2a');
	});
});
