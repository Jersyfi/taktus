# ADR-0334 — A residency rule may demand a provider's terms of a model

**Status:** accepted · extends ADR-0116 §2–§4, ADR-0281 §4 · UC-11.1 · DEC-0239

## Context

A tenant's residency rule says where its data may be processed: `own`, `eu` or `anywhere`
(ADR-0116 §3). A step on a model is routed only to a model whose declared location the rule
admits.

Location is not the only condition an organisation sets for a provider. Two others are common:

- **A data-processing agreement is in place.** Under the GDPR (Art. 28) a provider that processes
  personal data on the organisation's behalf needs a contract with it.
- **The provider does not train on the data.** Many providers offer terms under which the data
  sent is not used to train their models.

A model in the right location may lack either. Until now nothing let a tenant say "customer data
only to a provider with an agreement and without training", and nothing kept the route to it.

## Decision

### 1. A model declares the provider's terms

The operator declares, per model, the terms its provider has agreed:
`TAKTUS_MODEL_TERMS`, or `TAKTUS_MODELS_<MEMBER>_TERMS` for a member, comma-separated, out of
`processing-agreement` and `no-training`. A member without its own falls back to the instance's,
as for location (ADR-0116 §1). Nothing is declared by default. An unknown term is refused when
the configuration is read.

### 2. A tenant's rule may demand them

The residency rule gains two fields:

- `terms`: the terms demanded for all the tenant's data;
- `class_terms`: per data class, the terms demanded beside those.

The terms demanded for a step are the tenant's together with those of the step's data class.
A tenant that sets none demands none. `taktusctl residency set --terms …` and
`--class-terms <class>=<term>+<term>` set them; a change is the ledger entry
`residency.configured`, as before.

### 3. The route passes over a model without them

A member *fits* a step only when it declares every term the rule demands for the step's data, in
addition to the three conditions of ADR-0116 §4. A member passed over for this is recorded in the
route with the reason `terms`, which the provenance contract now admits
(`contracts/shared/v1/Provenance.json`). Where no member fits, the step fails with outcome
`no model`, naming each member and the terms it lacks. The data is sent to no model.

### 4. Registration holds a version to it

A version whose step on a model handles data for which the rule demands terms, and whose purpose
no admitted model with those terms serves, does not register (ADR-0281 §4). The finding names the
step, the data class and the terms.

## Alternatives

- **A location of its own, such as `eu-agreed`.** Rejected. Location and terms are independent:
  a model in the EU may train on the data, and one with an agreement may sit elsewhere. One
  ordered scale cannot express both.
- **Terms on the tenant's side only, as a list of permitted models.** Rejected. A tenant would
  have to know the instance's member names, and every new member would need every tenant's rule
  changed. The terms are a fact about the provider, declared once by the operator.
- **Read the terms from the provider.** No provider publishes its agreements through an
  interface. The declaration is the operator's, as the location is.

## Consequences

- `ports/model.py`: `TERMS`, `ResolvedModel.terms`.
- `composition/settings.py`: `TAKTUS_MODEL_TERMS`; `composition/execution.py` and
  `adapters/driven/models/pool.py` carry it to the member.
- `components/governance`: `ResidencyRule.terms`, `class_terms`, `demanded`; `TenantResidency`
  answers the run's new port `ProviderTerms`.
- `components/run`: the port, `Needs.terms`, the skip reason `terms`.
- `composition/residency.py`: the finding at registration.
- Tests: `tests/components/run/test_model_routing.py`,
  `tests/composition/test_residency_registration.py`.
- A rule without terms is written as the previous release wrote it (ADR-0093). No migration:
  the rule is a document.

## Where this promise ends

- **Declared, never verified.** Taktus holds a route to the operator's declaration. Whether the
  provider honours its agreement is the operator's and the provider's (UC-11.1 §3).
- **Models only.** A worker or a connector carries no declared terms. A worker that calls a model
  itself, and a connector that sends data to a service, are held to the location rule only.
- **The data class is the process's declaration** (UC-11.1 §3). Data a step sends without a
  declared class is held to the tenant's own terms, not to a class's.
- **No legal assessment.** Whether an agreement satisfies a law is the organisation's question.
