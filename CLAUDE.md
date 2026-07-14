"Read PROJECT_SPEC.md before any work. All code must conform to it, especially Sections 3, 4 (Engineering Standards), and 13 (Testing). We build phase by phase per Section 14 — never skip ahead."

## Autonomous Execution Protocol

When instructed to execute multiple phases autonomously, follow this loop
for each phase, in order:

1. PLAN: Re-read the phase definition in PROJECT_SPEC.md §14 and every
   section it references. Write the phase plan to docs/PROGRESS.md before
   coding.
2. BUILD: Implement per the spec and Engineering Standards (§4). Never
   weaken a standard to make progress; if the spec conflicts with reality,
   choose the conservative option and record it as an ADR.
3. VERIFY (hard gate): ruff, mypy --strict, frontend lint/typecheck, and
   the full test suite must pass before a phase is complete. Never skip,
   xfail, or delete a failing test to pass the gate — fix the code or
   record a blocker.
4. HANDOFF: NEVER run git commit, push, or any git history-modifying
   command — the maintainer commits personally. Instead, at the end of
   each phase output a ready-to-use commit message block:
   subject line "phase-N: <summary>" plus a body listing key changes,
   test counts, and ADRs added. Update docs/PROGRESS.md with what was
   completed before handing off.
5. CONTINUE to the next phase.

Asking questions: if a decision is genuinely ambiguous and choosing wrong
would be expensive to reverse (public API shape, data model, security
posture), PAUSE and ask the maintainer — one clear question with the
options and your recommendation. For small reversible choices, decide,
record it in PROGRESS.md, and continue. Never ask questions whose answer
is already in PROJECT_SPEC.md or an ADR.

Credentials & external services rule: NEVER invent, hardcode, or fake
API keys, URLs, or accounts. Build everything to be fully ready behind
the existing provider interfaces with mocked tests, so that supplying
real credentials is the ONLY remaining step. Every such requirement is
appended to docs/NEEDS.md as a checklist item with exact setup steps and
which env var it fills. Code that cannot be fully verified without the
resource is marked in PROGRESS.md as "built, pending live verification".

Stop conditions — halt the loop and summarize instead of continuing if:
(a) a verification gate cannot be made green without violating §4,
(b) a decision would change the public API or data model beyond the spec
    and the maintainer hasn't answered,
(c) all planned phases are complete.
On halt or completion, output: phases completed, docs/NEEDS.md contents,
open ADR candidates, and known risks — in that order.