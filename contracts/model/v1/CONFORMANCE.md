# Checking a model endpoint against the contract

This page is for someone who wants to know whether a model endpoint keeps what its adapter
declares about it, with or without a running Taktus. The contract and its four checks, M-01 to
M-04, are in [README.md](README.md) §2 to §5. You do not need to know anything else about Taktus to
follow this page.

---

## 1. What you need

- The endpoint: the base URL that serves `/chat/completions`, and the model name it is asked for.
- Its key in a file, if it needs one.
- Python 3.13 or newer, [`uv`](https://docs.astral.sh/uv/), and a clone of this repository with
  `uv sync` run in it.

The suite makes two calls to the model. They cost what two short calls cost.

---

## 2. Running it

```
export MODEL_API_KEY="$(cat "$TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE")"   # only if it needs one
uv run taktusctl conformance run --contract model/v1 --endpoint http://localhost:8000/v1 \
    --model the-model --credential MODEL_API_KEY --json report.json
```

Without `--declaration`, the suite judges the shipped adapter's default declaration: an
upper-bound count, a soft output limit, billing per token. With `--declaration declaration.json`
it judges the one in the file, in the shape of `Model.json#/$defs/Calculability`. The exit code
is `0` when every check passed, `1` when one failed, `2` when nothing failed but something could
not be proven.

---

## 3. What a pass means

A pass says that the endpoint kept the declaration on the two calls the suite made. A *verified*
model needs that and the removal test (`docs/architecture/contracts.md` §3), which a running
Taktus does as a process of its own.

**A report you run does not make a model *verified* in anybody's Taktus.** A Taktus instance
records this suite's half only when it ran the suite itself, against the model endpoint and the
model name its own configuration names (`taktusctl conformance record model.endpoint`,
ADR-0044). It judges the declaration its own model adapter makes: the output limit and the
billing basis configured as `TAKTUS_MODEL_OUTPUT_CAP` and `TAKTUS_MODEL_BILLING`. It records the
outcome with the model name and the purposes it serves. When either changes, the pass no longer
counts, and the instance needs to run the suite again.

---

## 4. Running the suite by hand, as an instance does

A person can run the same suite against the same endpoint without Taktus, and keep the report as
evidence. This is the way to check a model when no instance runs, and the way to repair one
(ADR-0013 B and C).

1. **Find the endpoint and the model**: `TAKTUS_MODEL_ENDPOINT` and `TAKTUS_MODEL_NAME`.
2. **Write the declaration the instance's adapter makes**, with the instance's
   `TAKTUS_MODEL_OUTPUT_CAP` and `TAKTUS_MODEL_BILLING`:

   ```json
   { "contract": "model/v1", "input_count": "upper_bound", "output_cap": "soft",
     "usage_kinds": ["input", "output"], "billing": "per_token" }
   ```

3. **Run the suite** as in section 2, with `--declaration declaration.json`.
4. **Keep the evidence together**: `report.json`, the declaration, the model name, the date, who
   ran it, and the commit of this repository the suite came from (`git rev-parse HEAD`). Put them
   where your organisation keeps evidence. The exit code says what the instance would record:
   `0` passed, `1` failed, `2` incomplete.

The report kept this way is evidence for a person. A Taktus instance does not import it: it would
be asserted, not measured by the instance.
