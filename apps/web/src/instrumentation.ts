import * as Sentry from "@sentry/nextjs";

// Next.js's native instrumentation hook (App Router) — runs once per
// server runtime before any route handles a request. Server-side half of
// Sentry wiring (§11, Phase 6); see instrumentation-client.ts for the
// browser half. A blank dsn is Sentry's own documented way to disable
// the SDK, so this never needs an if-configured branch.
export function register() {
  Sentry.init({
    dsn: process.env.SENTRY_DSN ?? "",
    environment: process.env.NODE_ENV,
    release: process.env.RELEASE_SHA ?? process.env.VERCEL_GIT_COMMIT_SHA ?? "dev",
    // A low tracesSampleRate gives free baseline latency data. (GlitchTip's
    // own setup docs also recommend `autoSessionTracking: false` — that
    // option no longer exists in this SDK version's types, per tsc; recent
    // @sentry/nextjs releases apparently dropped/renamed it.)
    tracesSampleRate: 0.01,
  });
}
