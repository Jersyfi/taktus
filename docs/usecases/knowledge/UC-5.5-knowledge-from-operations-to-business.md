---
id: UC-5.5
title: Knowledge, from the operational to the business
component: knowledge
epic: E5
serves: [P2, P4, P7]
state: verified
version: 0.5.0
tests: [tests/composition/test_knowledge_answers.py::test_k_01_answers_with_every_statement_naming_its_source_and_its_link, tests/composition/test_knowledge_answers.py::test_every_step_that_rests_on_knowledge_is_sourced_and_declares_its_check, tests/composition/test_knowledge_answers.py::test_an_answer_naming_a_document_the_asker_did_not_read_does_not_leave, tests/composition/test_knowledge_answers.py::test_an_answer_whose_statements_name_no_source_fails_its_check, tests/composition/test_knowledge_answers.py::test_two_identities_asking_the_same_get_only_what_the_wiki_shows_each, tests/composition/test_knowledge_answers.py::test_an_identity_without_an_own_credential_gets_nothing_from_the_source, tests/composition/test_knowledge_answers.py::test_the_index_keeps_references_and_digests_never_the_text, tests/composition/test_knowledge_answers.py::test_a_document_changed_while_the_answer_was_written_is_said_and_indexed, tests/composition/test_knowledge_answers.py::test_a_document_removed_while_the_answer_was_written_is_said_and_indexed, tests/integration/test_knowledge_removal.py::test_removing_the_knowledge_source_changes_what_is_known_and_breaks_no_process, tests/adapters/connectors/test_knowledge_search.py::test_two_tokens_with_different_rights_find_what_the_wiki_shows_each, tests/adapters/connectors/test_knowledge_search.py::test_versions_say_what_the_wiki_holds_now, tests/components/knowledge/test_citing.py::test_the_index_s_later_observation_is_said_too, tests/components/knowledge/test_index.py::test_a_changed_document_moves_its_old_version_into_the_history, tests/components/value/test_knowledge_comparison.py::test_the_same_work_with_and_without_a_source_is_compared_on_the_cockpit_figures, tests/components/value/test_knowledge_comparison.py::test_a_side_without_runs_withholds_its_figures_and_the_difference_never_zero, tests/composition/test_knowledge_value.py::test_the_same_work_with_and_without_the_wiki_is_compared_on_the_value_ledger, tests/adapters/rest/test_figures.py::test_the_same_work_with_and_without_a_knowledge_source_is_compared_for_whom_may_read_it]
adrs: {ADR-0003: d0268914fed9, ADR-0014: 6611f7833deb, ADR-0024: 52ba89e4adec}
supersedes: null
---

# UC-5.5 — Knowledge, from the operational to the business

## 1. What must be achieved

Taktus can draw on all the information that matters, however the organisation holds it: repositories
with their documentation, wikis and knowledge tools, shared drives, databases. From them it forms one
knowledge layer that joins operational knowledge — how is process X carried out? — with business
knowledge — why does process X exist, and what does it contribute?

Every statement Taktus makes from that knowledge names its source. Nobody learns through Taktus what
the source would not have shown them. The quality of Taktus's work rises demonstrably with the
knowledge connected.

## 2. How it is verified

- Every statement drawn from connected knowledge names the source it came from, with a link that
  opens it. A step whose result rests on knowledge is of class `sourced` or stricter (ADR-0014), and
  an answer without a source does not leave the step.
- The rights of the source system hold. A test with two identities whose permissions in the source
  differ asks both the same question, and each gets only what the source shows them. Taktus reads with
  the asker's rights, never with wider ones of its own.
- Every source is connected through a connector by capability (ADR-0003). Removing one changes what
  Taktus knows and breaks no process: the removal test.
- Taktus keeps an index, references and digests of what it read, so that it can find and cite it; the
  source stays the record. A source document changed or removed is reflected in the index, and an
  answer never cites a version the source no longer holds without saying so.
- The effect of connected knowledge on the quality of work is measured: the same work with and without
  a source connected is compared on the figures of the value ledger (UC-9.1).

## 3. Where the boundary lies

**Not a knowledge system.** Taktus replaces no wiki and no document store (principle 1); its index
is not a second record. **Not the data warehouse**, whose connection is UC-5.6. **Not a guarantee that
the source is right.** A cited statement is as good as its source; Taktus says where it came from, not
that it is true. **Not training a foundation model** on the organisation's knowledge
(`docs/vision/non-goals.md`).

## 4. What it rests on

The `knowledge` component, which owns knowledge sources, embeddings and citations
(`docs/architecture/project-structure.md` §1); the exactness class `sourced` (ADR-0014); connectors and
the adapter obligation (ADR-0003, ADR-0024); rights and least privilege (UC-7.3), sharing connectors per
circle (UC-8.8); a session with project knowledge (UC-1.8), which draws on this layer. Definition
`UC-5.5`. The roadmap's `0.3.0` names sessions with project knowledge; this use case is proposed there.

## 5. What is proven so far

Every condition of section 2. The comparison on the value ledger (ADR-0291) is proven with K-01
run with the wiki connected and without any connector on one ledger
(`tests/composition/test_knowledge_value.py`), by the rule that sorts runs into the two sides
and withholds a side without runs (`tests/components/value/test_knowledge_comparison.py`), and
at `GET /value/knowledge` (`tests/adapters/rest/test_figures.py`).
