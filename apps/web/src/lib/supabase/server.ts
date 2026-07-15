import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

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
 * Server-side Supabase client, for Server Components/Actions/Route
 * Handlers — reads/writes auth cookies via `next/headers`, per
 * `@supabase/ssr`'s standard Next.js App Router pattern. Same
 * publishable key as `lib/supabase/client.ts`'s browser client; it's the
 * cookie-aware request/response wiring that differs, not the credentials.
 *
 * Not wired to any feature yet — see `client.ts`'s docstring.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    requireEnv("NEXT_PUBLIC_SUPABASE_URL"),
    requireEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"),
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            for (const { name, value, options } of cookiesToSet) {
              cookieStore.set(name, value, options);
            }
          } catch {
            // Called from a Server Component, which can't set cookies —
            // fine as long as middleware refreshes the session (not set
            // up yet, since no auth flow exists to need it — see
            // client.ts's docstring).
          }
        },
      },
    },
  );
}
