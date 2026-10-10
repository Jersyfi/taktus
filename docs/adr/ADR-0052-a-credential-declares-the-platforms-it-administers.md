# ADR-0052 — A credential declares the platforms it administers

**Status:** accepted · makes ADR-0025 §1 checkable at planning time (issue #83)

## Context

ADR-0025 §1 says no instance runs on infrastructure it administers itself. *Administers* means
holding a credential that can change the infrastructure — namespaces, quotas, network policies,
node pools, storage classes, the platform's configuration — and running processes that use it.
Its section *Where this promise ends* says the rule is applied by the person who configures an
instance, and that refusing such a process is `0.2.0`.

Nothing lets planning see the rule. A step names a credential by its parameter only —
`REPOSITORY_TOKEN`, `CODING_AGENT_API_KEY` — and the operator maps the parameter to a value
(`TAKTUS_CREDENTIAL_<NAME>_FILE`, `CREDENTIALS.md`). Neither the step nor the mapping says what the
credential can change or which platform it reaches. Nor does an instance know, in a form planning
could compare, which platform it runs on. Reading a credential to find out what it can do would
mean calling the platform with it, which is the act the rule forbids.

## Decision

### 1. The instance names its platform
An instance is told the platform it runs on by one setting, `TAKTUS_PLATFORM`: an identifier the
operator chooses — a cluster's name, a host's — and never resolves. It is configuration, not
discovery: the operator knows where they installed the instance, and an instance that looked it up
would need the platform's API, which a well-bounded instance cannot reach.

### 2. A credential declares what it administers
Beside each credential parameter the instance maps, the operator declares the platforms it
administers, `TAKTUS_CREDENTIAL_<NAME>_ADMINISTERS`: a comma-separated list of platform
identifiers, or `none`. The declaration is the operator's statement about the credential, made
where the credential is mapped, by the person who created it. It is configuration and carries no
secret.

### 3. Planning refuses, and so does admission
Registering a process version reads every credential its steps name — in a connector step's
`credentials`, in a worker step's frame — and refuses the version when one of them declares that
it administers the instance's own platform, naming the step, the credential and the platform. The
run's admission checks the same again before every run, because a declaration can change after a
version was registered; a run refused there is a failure naming the same three.

### 4. What an undeclared credential counts as
Whether a credential without a declaration is refused, or admitted and reported, is what the
requirement says (UC-7.3, M3.15), and is asked in DEC-0133. The mechanism serves both: a
credential without `_ADMINISTERS` is *undeclared*, and the check returns it as such. While
`TAKTUS_PLATFORM` is unset, the instance says at start that the rule of ADR-0025 is not checked,
and registration and admission check nothing.

## Alternatives

- **Asking the platform what a credential may do** — `kubectl auth can-i` with the credential.
  Exact where it works, but it uses the credential against the platform, which is administering
  in the small; it needs the platform's API reachable from the control plane; and it knows only
  platforms Taktus has an adapter for.
- **Classifying credentials by name or by the capability that uses them.** A deployment's
  kubeconfig is not recognisable from its parameter name, and a connector's capability says what
  Taktus does with it, not what else it allows.
- **Declaring on the step, in the process bundle.** A bundle is portable between tenants and
  platforms; what a credential administers belongs to one instance's mapping, not to the process.

## Consequences

- An operator declares each credential once, where they already map it; the chart takes the
  declaration beside the credential (`credentials[].administers`) and the platform as a value.
- A process that would hand an instance its own platform is refused before it runs, with the
  reason, and the refusal is in the ledger.
- The removal test and conformance are unaffected: they read no declaration.

## Where this promise ends

The check is as true as the declarations. A credential declared `none` that can in fact change
the platform — a token with rights nobody listed — passes, and ADR-0025's own limit stands: such a
credential administers more than any rule sees. The platform's identifier is the operator's; two
names for one platform are two platforms to the check. The check covers credentials a step
*names*; a worker that obtains a credential by itself, outside its frame, is UC-7.3's frame rule,
not this one. Nothing here enforces anything on the platform: the platform's own boundary does
that (ADR-0025 §2).
