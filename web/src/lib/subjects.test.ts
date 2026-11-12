import { describe, expect, it } from 'vitest';
import { evidenceSentence, exportFile, notConfirmable, sayBack, type ProcessingEvidence, type SubjectRequest } from './subjects';

function request(over: Partial<SubjectRequest> = {}): SubjectRequest {
	return {
		id: 'dsr_1',
		kind: 'erasure',
		state: 'prepared',
		created_at: '2026-11-07T10:00:00+00:00',
		prepared_by: 'idn_dpo',
		carried_out_by: null,
		withdrawn_by: null,
		subject: 'cust-1',
		holds: { runs: 2, objects: 5, kept: 1, in_flight: [] },
		holdings: [],
		...over
	};
}

describe('a data-protection request', () => {
	it('is said back before it is carried out, and an erasure says it cannot be undone', () => {
		const said = sayBack(request());
		expect(said).toContain('checked who asked');
		expect(said).toContain('over 2 runs; 1 shared objects stay');
		expect(said).toContain('cannot be undone');
		expect(sayBack(request({ kind: 'access' }))).not.toContain('cannot be undone');
	});

	it('names the runs still in flight, which it leaves as they are', () => {
		expect(sayBack(request({ holds: { runs: 1, objects: 1, kept: 0, in_flight: ['run_9'] } }))).toContain(
			'One run is still in flight'
		);
	});

	it('is confirmable only while prepared', () => {
		expect(notConfirmable(request())).toBeNull();
		expect(notConfirmable(request({ state: 'carried_out' }))).toBe('This request is carried out.');
		expect(notConfirmable(request({ state: 'withdrawn' }))).toBe('This request is withdrawn.');
	});

	it('offers an export as a file and nothing where there is none', () => {
		expect(exportFile(request())).toBeNull();
		const file = exportFile(request({ kind: 'access', export: { subject: 'cust-1' } }));
		expect(file?.name).toBe('dsr_1-access.json');
		expect(JSON.parse(file?.text ?? '{}')).toEqual({ subject: 'cust-1' });
	});
});

describe('the processing evidence', () => {
	it('counts the steps and those outside the rule, and never claims compliance', () => {
		const step = {
			process: 'p',
			version: '1',
			step: 's',
			serves: 'connector.customers',
			personal_data: 'a case of one subject',
			adapter: 'a',
			location: 'eu',
			within_residency_rule: true
		};
		const evidence = {
			personal_data_steps: [step, { ...step, step: 't', within_residency_rule: false }]
		} as unknown as ProcessingEvidence;
		expect(evidenceSentence(evidence)).toBe(
			'2 steps process personal data, 1 of them outside the residency rule. Not legally reviewed.'
		);
	});
});
