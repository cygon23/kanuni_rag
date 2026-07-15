-- migrate:up

-- Completes migration 0003: schema_migrations (dbmate's own bookkeeping
-- table, not one of Kanuni's own) was deliberately left out there since
-- it's not "app data" — but it still lives in the public schema, so
-- Supabase's security advisor flags it exactly the same way. dbmate
-- connects as the table owner (same role as every app table), so this
-- has zero effect on migrations running — see 0003's comment for the
-- full owner-bypass-RLS reasoning, which applies identically here.

ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;

-- migrate:down

ALTER TABLE schema_migrations DISABLE ROW LEVEL SECURITY;
