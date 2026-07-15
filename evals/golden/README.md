# Golden evaluation sets

## `fixture_qa.jsonl`

12 items (10 answerable + 2 refusal), one small smoke-test set introduced in
Phase 2. Used as `run_retrieval_eval.py`'s default golden set and in CI.

## `qa.jsonl` — DRAFT, 62 items — NOT for public citation

**Status: DRAFT.** Generated in Phase 4 by an AI agent, derived from the real
text of the 6 Phase 1 fixture documents (citations, gazette numbers, section
references, and regulatory figures were read directly off the source PDFs —
nothing was invented). It is a reasonable starting point for exercising the
retrieval and answer eval harnesses end-to-end, **not** a validated benchmark.

Before any result computed against this file is cited publicly (in a report,
a README badge, a stakeholder update, etc.), a domain expert must:

1. Review every item for legal/regulatory accuracy, not just textual
   grounding in the fixture — a question can be faithfully derived from the
   PDF text and still be a poor or misleading eval question.
2. Replace or rewrite items that don't reflect the kinds of questions real
   users will ask.
3. Verify the 12 `must_refuse: true` items still describe topics genuinely
   absent from whatever corpus is live at review time (the corpus will grow
   past these 6 fixtures; a refusal item can go stale if a later ingestion
   adds coverage for its topic).
4. Confirm `ideal_answer_points` are complete and correctly stated — they
   currently reflect the drafting agent's reading of the source PDFs, not an
   independent legal review.

Items with `relevant_document_filename: null` and `must_refuse: true` are
out-of-corpus refusal probes (tax/TRA, EAC customs, other regulators/
jurisdictions, real-time data, unrelated law) — none of these reference
Bank of Tanzania regulatory content.

Two items (gd-039, gd-040) intentionally probe metadata that is blank on the
source PDF (gazette number/date for the Electronic Money Regulations, 2015);
the ideal answer is an honest "not available," not a guess. This is a
calibration check for fabrication, not a refusal item.
