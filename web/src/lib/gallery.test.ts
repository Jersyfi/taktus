// The gallery in the web app (UC-10.4, ADR-0136 §5): each blueprint with whom it is for, each
// process with its steps in words, its level and why, and its choices prefilled; a process not
// offered says why and offers no choosing; an empty gallery says a process can still be
// registered from its file. The plan dialogue shows a process with no version yet as its first.

import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ChangeView from './ChangeView.svelte';
import GalleryView from './GalleryView.svelte';
import type { GalleryBlueprint, Proposal } from './types';

const nothing = () => {};

const BLUEPRINTS: GalleryBlueprint[] = [
	{
		id: 'household',
		title: 'A household',
		for: 'a household',
		summary: 'A weekly note.',
		processes: [
			{
				id: 'weekly-note',
				name: 'The weekly note',
				reason: 'every week, a note',
				level: 2,
				level_reason: 'a person confirms each step',
				steps: [{ id: 'write', method: 'rule', reason: 'a fixed form of words' }],
				choices: [{ name: 'who', label: 'Who the note is for', value: 'the Smiths' }]
			},
			{ id: 'too-free', name: 'Too free', reason: '', refused: ['it starts at autonomy level 3'] }
		]
	}
];

describe('the gallery offers a first process (UC-10.4)', () => {
	it('shows each process with its steps in words, its level and its choices prefilled', () => {
		const html = render(GalleryView, { props: { blueprints: BLUEPRINTS, onChoose: nothing } }).body;
		expect(html).toContain('A household');
		expect(html).toContain('For a household.');
		expect(html).toContain('By a fixed rule: a fixed form of words.');
		expect(html).toContain('It starts at autonomy level 2: a person confirms each step.');
		expect(html).toContain('Who the note is for');
		expect(html).toContain('value="the Smiths"');
		expect(html).toContain('Make this my first process');
	});

	it('says why a process is not offered, and offers no choosing for it', () => {
		const html = render(GalleryView, { props: { blueprints: BLUEPRINTS, onChoose: nothing } }).body;
		expect(html).toContain('Not offered: it starts at autonomy level 3');
		expect(html.match(/Make this my first process/g)?.length).toBe(1);
	});

	it('says an empty gallery is empty, and that a process can still be registered', () => {
		const html = render(GalleryView, { props: { blueprints: [], onChoose: nothing } }).body;
		expect(html).toContain('data-empty');
		expect(html).toContain('registered from its file');
	});
});

describe('the plan dialogue shows a process with no version yet as its first (ADR-0136 §4)', () => {
	const first: Proposal = {
		id: 'prp_1',
		process_id: 'weekly-note',
		version: '1',
		request: 'from the gallery: A household',
		state: 'proposed',
		created_at: '2026-10-23T10:00:00Z',
		difference: { steps: [{ id: 'write', change: 'added', after: { id: 'write', method: 'rule', reason: 'words' } }] },
		bundle: { name: 'The weekly note' }
	};
	const handlers = { onAsk: nothing, onRehearse: nothing, onCommission: nothing, onDiscard: nothing, onRollback: nothing };

	it('names it its first version, offers the rehearsal, and no request in words and no versions', () => {
		const html = render(ChangeView, {
			props: { level: null, processId: 'weekly-note', proposals: [first], ...handlers }
		}).body;
		expect(html).toContain('The weekly note · a new process');
		expect(html).toContain('its first version');
		expect(html).toContain('>Rehearse<');
		expect(html).toContain('back to the gallery');
		expect(html).not.toContain('Ask Taktus');
		expect(html).not.toContain('aria-label="Versions"');
		expect(html).not.toContain('Commission version');
	});
});
