---
id: UC-6.1
title: The complete activity log
component: ledger
epic: E6
serves: [P6, P11, P12]
state: building
version: 0.5.0
tests: [tests/components/ledger/test_chain.py::test_entries_link_and_verify, tests/components/ledger/test_chain.py::test_an_altered_field_is_found, tests/components/ledger/test_chain.py::test_a_removed_entry_is_found, tests/components/ledger/test_chain.py::test_a_reordered_chain_is_found, tests/components/ledger/test_chain.py::test_a_fact_carries_no_text, tests/components/ledger/test_chain.py::test_the_hash_rule_is_the_documented_one, tests/components/run/test_engine.py::test_a_run_completes_and_every_state_change_is_in_the_ledger, tests/components/run/test_provenance.py::test_every_completed_step_has_one_record_bound_to_its_ledger_entry]
adrs: {ADR-0006: 4ef70c98354b, ADR-0021: 202e0442e7ec, ADR-0022: 69572977f46b}
supersedes: null
---

# UC-6.1 — The complete activity log

## 1. What must be achieved

Every action Taktus takes is recorded so that it can be audited: what was done, when, why, by
which method — and for a model or a worker, which one — at what cost, and with what result. The
record cannot be changed afterwards without the change being found. It is complete enough that
a person who was not there can reconstruct what happened, and it holds no content it does not
need: it references documents and data, it does not copy them.

## 2. How it is verified

- Every change of state of a run and of a step, every command received, every decision recorded
  and every outward effect is an entry of the ledger, in sequence, with its time.
- The entry of a completed step, with its provenance record, names what produced the result —
  the method, and for a model or worker which one in which version — what it consumed, and the
  result by reference. The reason for the method is reachable from the entry through the process
  version the run used.
- Altering a field, removing an entry or reordering entries is found by verification, including
  an alteration whose own hash was recomputed.
- An entry carries no free text and no copy of a document or a personal datum; it carries
  identifiers, tokens and digests (ADR-0006).
- The chain can be exported and verified outside Taktus, by anyone with the export and the
  documented hash rule, without Taktus running.
- The log can be exported as a telemetry signal, entry by entry, with nothing the ledger itself
  would not carry.

**Proven so far:** the first four conditions, by the named tests. The export, a verification
outside Taktus, and the export as a telemetry signal do not exist.

## 3. Where the boundary lies

**Not the views.** Who sees which part of the log, and how it is shown, is `reporting`'s
(UC-6.4). **Not the content.** The log says that a document was read and which one; the document
lives where it lives, under that system's rights. **Not a log of people.** Entries name roles and
the identities that acted; no figure about a named person is derived from them (principle 14).
**Not an operational log.** Log lines and traces for running the system are telemetry, not this
record, though every ledger entry carries the trace identifier that links them. Exporting this
record as a telemetry signal is in this use case (section 2); the export does not make the
telemetry the record.

## 4. What it rests on

The ledger as a content-free hash chain (ADR-0006); the provenance record of every completed
step (ADR-0021); egress entries for every outward effect (ADR-0022). Definition `UC-6.1`. The
version is `0.5.0`, where the roadmap measures principles 6 and 13; the chain itself is `0.1.0`
and built.
