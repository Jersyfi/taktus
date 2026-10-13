# NTC-0205 — The project's values become settings

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-13
**Raised in:** the pull request for issue #313

## 1. What was decided

ADR-0092 says nothing of the Taktus project is product (DEC-0188). Issue #313 named the leaks.
This notice records how each was removed and which behaviour of an instance changes with it.
ADR-0092's amendment of 2026-10-13 states the same as a rule.

1. **A fresh install starts uncalibrated.** The product ships no calibration seed. A worker
   nothing has measured reserves twice its estimate (DEC-0034), the coding worker included.
   An operator who wants a seed names a file of them with `TAKTUS_BUDGET_SEEDS`.
2. **`taktusctl guides` needs the manifest's path.** It is given with `--manifest` or
   `TAKTUS_GUIDES_MANIFEST`. Without it the command refuses. Before, it read
   `docs/guides/guides.yaml`, this repository's place.
3. **The chart's `model.outputCap` defaults to `soft`.** Before, it was `hard`, the value
   measured on the project's endpoint.
4. **A finding has the product's plain shape unless its operator gives a form.**
   `TAKTUS_FINDINGS_FORM` names a file with the body's form. `TAKTUS_FINDINGS_LABELS` names
   the labels. Before, every finding took the sections of this repository's issue form and the
   label `task`.
5. **A change in words needs a named process.** `TAKTUS_CHANGE_PROCESS` names the process that
   turns a request in words into a proposal. Without it the request is refused, and the change
   is handed over as a bundle. Before, the product looked for the project's process
   `s07-change-in-dialogue` by its identifier.
6. **The chart mounts files of configuration.** `configFiles` maps a file name to its content.
   Every role reads it at `/etc/taktus/files/<name>`. That is how a seed file or a form reaches a
   pod on a cluster.
7. **Texts name no project process.** The REST description of a change in words no longer
   names S-07. The example in a configuration error names `triage`, not `p05-triage`. A page of
   the guides says it was generated "from the repository", not "from the Taktus repository".

The project's own values stay in this repository as documents: the seed in
`docs/runs/first-run.seeds.yaml`, the finding's form in `.github/finding-form.md`. Its
operator loads them; `deploy/k8s/README.md` §2 lists every value the project's instance sets.

## 2. The evidence

- `tests/architecture/test_no_project_in_the_product.py` reads every string of `src/` that is
  not a docstring, and every value of the chart's `values.yaml`. Against `main` before this
  change it finds `s07-change-in-dialogue` in `composition/proposals.py` and `S-07` twice in
  `adapters/driving/rest/proposals.py`. The project's process identifiers come from the bundles
  under `blueprints/`, the owner from `LICENSE` and `.github/CODEOWNERS`.
- `tests/components/run/test_budget.py` shows that without a seed the coding worker reserves
  120 000 input tokens for an estimate of 60 000. With the project's seed file loaded it
  reserves 257 289, as the shipped seed did.
- `tests/composition/test_settings.py`, `tests/components/reporting/test_product_findings.py`,
  `tests/integration/test_findings_command.py`, `tests/integration/test_guides_command.py` and
  `tests/composition/test_proposals.py` show each setting's default and its configured value.
  `tests/governance/test_chart.py` shows `configFiles` and the default output limit; it needs
  helm.

## 3. What was considered

- **Keeping the project's values as an optional mode of the product.** Not taken: ADR-0092
  rejects a product mode for the project.
- **Settings that carry the seed and the form as text in an environment variable.** Not taken:
  a seed of eight observations and a form of several sections are documents. A file keeps them
  readable and reviewable, as the price table is (`TAKTUS_PRICE_TABLE`).
- **One chart key per file (`budget.seeds`, `findings.form`).** Not taken: each new file setting
  would need its own template. `configFiles` serves every setting that names a file.
- **Leaving the identifier of the change process as the product's default.** Not taken: S-07 is a
  bundle of the project's tenant (`blueprints/self-operation/`). Another tenant registers its
  own, under its own identifier, or none.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #313 and ADR-0092, which the owner accepted (DEC-0188). No contract
under `contracts/` changes. No limit moves: the seed changes what a worker reserves inside a
budget, not the budget, and every value removed is still available to an operator as a
setting. Nothing public is said.
