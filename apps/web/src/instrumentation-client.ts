import * as Sentry from "@sentry/nextjs";

// Next.js's native client-side instrumentation entry point (bundled and
// run before the app starts). Browser half of Sentry wiring (§11, Phase
// 6) — see instrumentation.ts for the server half.
//
// Sentry DSNs are meant to be public (they only allow submitting events,
// not reading data) — unlike KANUNI_API_KEY, this is safe as
// NEXT_PUBLIC_*. A blank dsn disables the SDK.
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN ?? "",
  environment: process.env.NODE_ENV,
  release: process.env.NEXT_PUBLIC_RELEASE_SHA ?? "dev",
  // A low tracesSampleRate gives free baseline latency data. (GlitchTip's
  // own setup docs also recommend `autoSessionTracking: false` — that
  // option no longer exists in this SDK version's types, per tsc; recent
  // @sentry/nextjs releases apparently dropped/renamed it.)
  tracesSampleRate: 0.01,
});
