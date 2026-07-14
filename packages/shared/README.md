# @kanuni/shared

Shared TypeScript types for the frontend, generated from the API's OpenAPI
schema. Populated starting Phase 5 (§14) once `apps/api` exposes real
endpoints — for now this package is intentionally empty scaffolding.

Regeneration (once wired up): the API's OpenAPI spec is exported and run
through an OpenAPI-to-TypeScript codegen step into `src/generated/`.
