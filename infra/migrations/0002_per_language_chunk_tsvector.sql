-- migrate:up

-- Implements ADR 0004: PostgreSQL has no 'swahili' text-search config, so
-- 'content_tsv' must select a config per chunk's language rather than
-- always using 'english'. language is denormalized from documents.language
-- at insert time (chunks has no FK-joinable language of its own) so the
-- generated column expression can branch on it directly.

ALTER TABLE chunks ADD COLUMN language text NOT NULL DEFAULT 'en';

DROP INDEX chunks_content_tsv_gin_idx;
ALTER TABLE chunks DROP COLUMN content_tsv;
ALTER TABLE chunks ADD COLUMN content_tsv tsvector GENERATED ALWAYS AS (
    to_tsvector(
        CASE WHEN language = 'sw' THEN 'simple'::regconfig ELSE 'english'::regconfig END,
        content
    )
) STORED;
CREATE INDEX chunks_content_tsv_gin_idx ON chunks USING gin (content_tsv);

ALTER TABLE chunks ALTER COLUMN language DROP DEFAULT;

-- migrate:down

ALTER TABLE chunks ADD COLUMN content_tsv_old tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
DROP INDEX chunks_content_tsv_gin_idx;
ALTER TABLE chunks DROP COLUMN content_tsv;
ALTER TABLE chunks RENAME COLUMN content_tsv_old TO content_tsv;
CREATE INDEX chunks_content_tsv_gin_idx ON chunks USING gin (content_tsv);
ALTER TABLE chunks DROP COLUMN language;
