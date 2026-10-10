# NTC-0123 — A figure observed in operation is a histogram

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#183](https://github.com/Jersyfi/taktus/issues/183), in the pull request that closes it

## 1. What was decided

The telemetry port records histograms beside spans: `observe(name, value, unit)`. Before, it
recorded spans only. ADR-0055 §7 asks that the time from a ledger entry's recorded moment to its
hand-over to a reader be observed in operation, not only in a test; a span cannot carry that.

The OpenTelemetry adapter keeps a meter provider of its own. Where `TAKTUS_OTLP_ENDPOINT` is
set, it exports the histograms every 30 seconds to the same collector as the spans: over gRPC to
the same endpoint, over HTTP to `/v1/metrics` in place of `/v1/traces`. Without an endpoint
nothing is exported, as for spans. The first histogram is `change.handover`, in seconds. It
carries no attribute, so that it names no tenant, run or person.

## 2. The evidence

- ADR-0055 §7 and issue #183, "How it is verified": *"The time from an entry's recorded moment to
  its hand-over is a telemetry histogram."*
- `tests/composition/test_live.py`: a change handed over records one observation of
  `change.handover` in seconds.
- `tests/adapters/telemetry/test_histograms.py`: a histogram reaches a metric reader with its
  unit, and an attribute name that is not a dotted lowercase token is refused, as for spans.

## 3. What was considered

- **A span per hand-over with the delay as an attribute.** Rejected: a span per change per
  reader is a trace nobody reads, and a collector cannot draw a distribution from attributes.
- **A second endpoint setting for metrics.** Rejected: one collector receives both in every
  deployment the repository describes; a second setting can follow when one does not.
- **Label the histogram with the tenant.** Rejected: an attribute per tenant grows with the
  tenants, and the figure is the replica's.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #183;
the telemetry port is internal, and what reaches the operator's collector is one more signal of
the kind `docs/architecture/control-plane.md` §8 already promises. No limit or level moves.
