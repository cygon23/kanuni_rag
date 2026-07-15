-- migrate:up

-- Every app table was created with RLS disabled (Postgres/Supabase's
-- default), which Supabase's security advisor flags: on Supabase, the
-- REST/GraphQL layer (PostgREST) and any anon/authenticated client key
-- read the `public` schema directly, so a table with RLS off is readable
-- by anyone holding the anon key the moment it's ever exposed — even
-- though *today* apps/api is the only thing that talks to this database,
-- and it does so as the table owner (postgres.<project-ref> in Supabase's
-- pooler, or the migration role locally).
--
-- Postgres exempts table owners and superusers from RLS by default
-- (only `FORCE ROW LEVEL SECURITY` changes that, which we deliberately
-- do NOT set here) — so enabling RLS with zero policies is exactly the
-- right shape for this codebase: apps/api's own connection (the owner)
-- keeps working completely unchanged, while every other role (anon,
-- authenticated, or any future PostgREST/Supabase-client access) gets
-- default-deny, since no policy grants them anything. No application
-- code change is required for this migration to be safe.
--
-- If a table ever needs direct client-side access (e.g. a future
-- Supabase Storage/Realtime integration querying `documents` directly
-- instead of through apps/api), add explicit, scoped policies for that
-- table at that time rather than turning RLS off again.

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_relations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE queries ENABLE ROW LEVEL SECURITY;

-- migrate:down

ALTER TABLE documents DISABLE ROW LEVEL SECURITY;
ALTER TABLE chunks DISABLE ROW LEVEL SECURITY;
ALTER TABLE document_relations DISABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs DISABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys DISABLE ROW LEVEL SECURITY;
ALTER TABLE queries DISABLE ROW LEVEL SECURITY;
