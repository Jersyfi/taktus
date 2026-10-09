# Blueprints

A **blueprint** is one domain of a business — a department — described as a curated bundle that
conducts the systems the organisation already has: which recurring processes the domain has, which
connector capabilities they need, which autonomy level is usual for each and why, which figures the
domain's value balance keeps, and which acts stay with a person by law. An organisation instantiates a
blueprint in dialogue, starting at a conservative autonomy level, and adapts it. What a blueprint must
be is use case UC-15.1 (`docs/usecases/catalog/UC-15.1-domain-blueprints.md`); who is responsible for an
instantiated domain is UC-15.5.

A blueprint is a deployment of the core, not a capability of it. Its processes name systems by
capability only, so that replacing the accounting system or the customer system behind a domain breaks
none of them.

## The blueprints of this repository

| Blueprint | What it is | State |
|---|---|---|
| [`dev-orchestration`](dev-orchestration/README.md) | product development, unattended — use case UC-01 | three of eleven processes run as bundles |
| [`self-operation`](self-operation/README.md) | what Taktus runs for itself, on itself | S-01 the removal test runs weekly |
| [`it-operations`](it-operations/README.md) | systems operation, unattended — use case UC-02 — and its reference assistant, the IT service chat (UC-12.2) | a description; the roadmap's `0.7.0` |
| [`finance`](finance/README.md) | the finance reference domain under legal anchors — UC-15.2 | a description; not on the roadmap |

## Example domains

Domains a blueprint can describe. The list is extensible and never complete. For each, the recurring
work Taktus can take over and what stays with a person, both as examples. Which acts are legal anchors
in a domain is its legal-anchor catalogue (UC-15.5), reviewed per jurisdiction by people with that
expertise before a finance or personnel blueprint is used (DEC-0029).

| Domain | Recurring work Taktus takes over (examples) | Stays with a person |
|---|---|---|
| **Technology and IT** (reference: `dev-orchestration`, `it-operations`) | refining tickets, implementing, reviewing, repository hygiene, handling vulnerabilities, the IT service chat (UC-12.2) | architecture, product decisions, merging into protected areas as the policy says |
| **Finance and accounting** (reference: `finance`, UC-15.2) | capturing documents, proposing how to account for them, matching payments, preparing reminders, preparing tax pre-filings and closings, handing over to the tax adviser | releasing payments above a threshold, signatures, the tax return, the annual accounts |
| **Sales and customer relations** | qualifying leads, drafting offers from price lists, follow-ups, keeping the pipeline current, a sales FAQ (UC-12.3) | price negotiation, concluding contracts, the customer relationship |
| **Purchasing and procurement** | bundling demand, comparing offers, placing orders as the policy allows, rating suppliers on data, matching goods received | choosing a supplier where the choice is strategic, negotiating contracts |
| **Partners and interfaces** (reference: UC-15.3) | importing and exporting orders, invoices, catalogues and master data; validation, mapping, replies to partners | the partnership, data contracts, disputes |
| **Customer service** | first answers, searching knowledge, creating tickets, status information, escalation with context (UC-4.5) | goodwill decisions, complaints that affect the relationship |
| **Marketing and communication** | drafting content, reporting on campaigns, keeping channels current to an editorial plan | positioning, releasing anything said in public |
| **Personnel, administrative** | onboarding and offboarding procedures, producing documents, deadlines, organising training | every personnel decision; **no assessment of performance** (principle 14) |
| **Legal and compliance** | the record of processing activities, conformity evidence, watching deadlines, drafting contracts from templates | legal assessment, signature, negotiation |
| **Operations and administration** | facility reports, ordering office supplies, coordinating appointments, filing documents | budget decisions |

Where the original definition names escalation as `UC-4.6`, this repository numbers it `UC-4.5`
(`docs/usecases/NUMBERING.md`).

The same pattern carries privately: a household's finances, appointments and errands can be the domains
of a family.
