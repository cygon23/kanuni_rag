# 0003. Store the raw rerank score in `queries.confidence`; derive the tier at read time

## Context

PROJECT_SPEC.md §6 lists `queries.confidence` without specifying its type.
§8.2 defines a confidence *gate* with two named tiers derived from
thresholds (`CONFIDENCE_REFUSE_THRESHOLD`, default 0.30;
`CONFIDENCE_CAUTION_THRESHOLD`, default 0.55) applied to the top
cross-encoder rerank score. §8.2 also requires these thresholds to be
"calibrated against the golden dataset," and §15 requires an ADR on the
calibration method once that work happens.

## Decision

`queries.confidence` is a `double precision` column storing the **raw** top
rerank score for that query (e.g. `0.42`), not a categorical tier. The tier
(`refuse` / `low` / `ok`) shown to the client and used for the
caution-banner decision is derived at read time by comparing the stored
score against the current threshold config — it is never persisted.

## Alternatives considered

- **Store the tier as an enum/text column instead of the raw score.**
  Rejected: it would throw away the information the future threshold-
  calibration work (§15) actually needs. Recalibrating thresholds against
  historical query logs requires the original scores; a stored tier
  computed under yesterday's thresholds becomes wrong (not just stale) the
  moment thresholds change.
- **Store both the raw score and the tier.** Rejected for v1 as redundant:
  the tier is a pure function of `(confidence, thresholds_at_read_time)`
  and computing it is cheap. Revisit if read-time computation ever becomes
  a measurable cost.

## Consequences

- Any future analytics or calibration script reads raw `queries.confidence`
  values directly — no join or reverse-engineering of "what tier did this
  used to be" is needed.
- The API response layer (Phase 3) is responsible for computing the tier
  from `confidence` + current config on every read; this must stay a pure,
  well-tested function since it's the only place the tier is materialized.
- If thresholds change, all *future* answers reflect the new thresholds
  immediately; re-deriving tiers for *past* answers (e.g. for a dashboard)
  requires re-running the same pure function over historical rows, which is
  supported precisely because the raw score was kept.
