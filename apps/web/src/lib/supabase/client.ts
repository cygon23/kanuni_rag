import { createBrowserClient } from "@supabase/ssr";

function requireEnv(
  name: "NEXT_PUBLIC_SUPABASE_URL" | "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not set — see .env.example.`);
  }
  return value;
}

/**
 * Browser-side Supabase client, for Client Components. Uses the public
 * publishable key (safe to bundle client-side — it's the whole point of
 * that key, unlike the service-role key `apps/api`/`apps/ingestion` use
 * server-side for storage writes; see docs/NEEDS.md).
 *
 * Not wired to any feature yet (apps/web talks to Supabase only
 * indirectly, through apps/api — see lib/serverConfig.ts) — this exists
 * so a future feature (Supabase Auth, Realtime, direct client-side
 * Storage reads) has the standard SSR-package client ready to import
 * rather than being scaffolded ad hoc when the need shows up.
 */
export function createClient() {
  return createBrowserClient(
    requireEnv("NEXT_PUBLIC_SUPABASE_URL"),
    requireEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"),
  );
}
