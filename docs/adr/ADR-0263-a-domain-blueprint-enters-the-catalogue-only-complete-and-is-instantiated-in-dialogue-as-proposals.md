# ADR-0263 — A domain blueprint enters the catalogue only complete, and is instantiated in dialogue as proposals

**Status:** accepted · extends ADR-0011, ADR-0026, ADR-0136 · UC-15.1 §2 · DEC-0228

## Context

A **domain blueprint** describes one department of a business: the recurring processes it has,
the connector capabilities they need, the usual autonomy level of each with its reason, the
figures its value balance keeps, and the acts that stay with a person (UC-15.1 §1). The
repository holds such files under `blueprints/<name>/blueprint.yaml`. Nothing read them. The
bundle check skipped them as no process (`tests/integration/test_bundle_check_command.py`). One
of them lacked value criteria and anchors, one named capabilities its bundles did not use and
left out ones they did, and the blueprint of the second tenant had none at all.

UC-15.1 §2 asks five things of a blueprint and its instances. A blueprint missing a part does
not enter the catalogue. An organisation instantiates it in dialogue: Taktus asks for the tools
that exist, binds them by capability, and starts every process at level 1 or 2. No process of
an instance runs before the domain has its one named owner. A later version of the blueprint is
offered as a proposal and never applied on its own. A blueprint leaves Taktus as plain files.

The pieces exist. A proposal is a bundle held to every check of registration that registers
nothing until a person commissions it (UC-4.15, ADR-0091). The gallery already makes a chosen
process a proposal at level 2 or below (ADR-0136). The removal test exercises a process with
an adapter withheld (ADR-0030).

## Decision

### 1. The admission of a blueprint is a rule with every finding

The catalog component's rule (`catalog/domain/service/blueprints.py`) admits a blueprint
document or refuses it with every reason it fails. A blueprint is admitted only when all of
the following hold:

- It is of kind `Blueprint` and names its `id`, `name`, `domain` and `version`.
- It names at least one process. Each process has an identifier that is unique in the
  blueprint, and a name.
- Each process has a usual autonomy level from 1 to 4 and a reason for it (ADR-0026). A process
  that names its bundle with `bundle:` takes both from the bundle. The bundle must pass the
  checks registration applies to a bundle on its own (`parse_bundle`), and a level the
  blueprint also states must equal the bundle's.
- Every connector capability is named in the form `area.object`. Every capability an operation
  of a bundle calls is in `requires.connectors`. A capability is a name, never a product name
  (ADR-0003).
- It names value criteria, at least one of cost and one of benefit.
- It names at least one strategic or legal anchor: an act that stays with a person (UC-15.5).

The rule calls nothing. The composition root reads the files and hands it what each bundle came
to under `parse_bundle` (`composition/domain_blueprints.py`). Every blueprint of this repository
is held to the rule by a test, so a blueprint that misses a part fails CI and never ships.

Two processes whose bundles are versions of the same process are alternatives of one another:
the shipped blueprint of software operations has two such pairs. An instance keeps one of them.

### 2. An instance is a record of a dialogue

`DomainInstance` (catalog component, table `domain_instance` of migration 0106) is one domain an
organisation instantiated. It holds the blueprint and the version it was instantiated from, who
started it, one answer per required connector capability, the processes left out, the named
owner, and every process it proposed with the proposal and the digest of the bundle file.

The dialogue is the list of open questions the rule derives from the record:

- one per required capability not yet answered, with the adapters that declare it as its
  options;
- one per set of alternatives of which more than one is kept;
- one for the owner, while none is named.

A capability is answered with an adapter that declares it, or with `none`: the organisation has
no such tool. An answer naming an adapter that does not declare the capability is refused. The
owner must be an identity the tenant knows.

### 3. Processes are proposed only once the dialogue is closed, and at level 2 or below

`DomainInstances.propose` refuses while a question is open, the owner's among them. It then
makes each kept process with a bundle a proposal through `Proposals.propose`, at the lower of
its usual level and 2. The proposal's autonomy reason names the usual level and its reason, so
the way up stays visible (UC-7.1). A proposal registers nothing. A person commissions it (ADR-0091
§4). This is how the instance's processes start: proposed only once the domain has an owner, and
never above level 2.

### 4. A later version is offered, never applied

`DomainInstances.offer` takes a later version of the blueprint. For each process the instance
proposed whose bundle file changed, it makes a proposal of the changed bundle, under the next
version the tenant has not registered. The instance keeps the version it was instantiated from.
Its active versions, triggers and runs are unchanged. A process new in the later version is
named in the offer and is not proposed.

### 5. A blueprint leaves as plain files, and its figures are counted per domain

`taktusctl domain export` copies an admitted blueprint's `blueprint.yaml` and the bundle files
it names into a directory. Each is plain YAML that a person reads without Taktus.

The runs of an instance's processes are counted per domain from the run records, by process and
by state; a rehearsal is not counted (`catalog/domain/service/blueprints.py` `figures`).

### 6. The command line

`taktusctl domain` (`adapters/driving/cli/domain_command.py`) has `check`, `export`, `start`,
`answer`, `leave-out`, `owner`, `propose`, `show` and `offer`. A blueprint is named by its
directory.

## Alternatives

- **A third kind of entry in the signed catalogue's index.** The catalogue contract would gain a
  kind, and its readers would have to be compatible with it. A blueprint is files a person reads;
  its bundles can already be signed entries of an index. The index may name blueprints later,
  without changing this rule.
- **Register the processes at once, at level 1.** It would be faster. It would also put
  processes into production that no person commissioned, against UC-1.2 and ADR-0091.
- **Apply a later version to every instance.** It would keep instances current. It would also
  overwrite what the organisation adapted, against UC-15.1 §1: a blueprint is a template, not a
  corset.

## Consequences

- `catalog/domain/model/blueprint.py`: `DomainBlueprint`, `BundleFacts`, `DomainInstance` and
  their parts.
- `catalog/domain/service/blueprints.py`: the admission, the questions, the starting level, the
  offer and the figures.
- `catalog/application/service/domains.py`: `DomainInstances`, over the ports
  `catalog/ports/domains.py` (`ProcessProposals`, `People`, `Adapters`).
- `composition/domain_blueprints.py`: the files read, the ports answered from the process and
  identity components and from the release's list of connectors, the export.
- `blueprints/*/blueprint.yaml`: each one admitted; `blueprints/software-operations/blueprint.yaml`
  new.
- Tests: `tests/components/catalog/test_blueprints.py`, `tests/composition/test_domain_blueprints.py`,
  `tests/integration/test_domain_removal.py`.

## Where this promise ends

- The rule checks that each part is present and well formed. It does not judge whether the
  anchors are the right ones. The acts that stay with a person in a finance or personnel
  blueprint are reviewed per jurisdiction by people before it is used (DEC-0029).
- A capability is checked for its form, not for its meaning. A product's name written in that
  form would pass the rule. The architecture tests and review keep product names out of the
  bundles.
- The instance records which adapter serves each capability. Deploying that connector and
  providing its credential stay with the operator (`TAKTUS_CONNECTORS`, `CREDENTIALS.md`).
- The owner named in the instance is the instance's own record. Holding a domain's owner across
  the governance of the tenant, including the owner who leaves, is UC-15.5's.
- The value balance per domain counts runs. The balance of cost against benefit with the
  organisation's own criteria is UC-9.3, which is not built; until it is, the value criteria a
  blueprint names are stated, not computed.
