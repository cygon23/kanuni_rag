# Prompts

Versioned prompt files live here (e.g. `answer_v1.md`), never as inline
strings in code. The active version is selected via
`Settings.active_prompt_version` (`KANUNI_ACTIVE_PROMPT_VERSION`).

- `answer_v1.md` — the query-path system prompt (§8.3): answer only from
  provided chunks, cite as `[chunk:<id>]`, disclose non-`in_force` sources,
  treat context as untrusted data.
