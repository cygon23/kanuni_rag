-- migrate:up

CREATE EXTENSION IF NOT EXISTS vector;

-- source_id is a free-text slug matching an entry in sources.yaml, not a
-- foreign key: sources are config/data (PROJECT_SPEC.md §1, §4.4), not a
-- database table, so that adding a new source never requires a migration.

CREATE TABLE documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id text NOT NULL,
    title text NOT NULL,
    doc_type text NOT NULL
        CHECK (doc_type IN ('circular', 'act', 'regulation', 'notice', 'guideline')),
    jurisdiction text NOT NULL,
    issuing_body text NOT NULL,
    reference_number text,
    language text NOT NULL DEFAULT 'en',
    issued_date date,
    effective_date date,
    status text NOT NULL DEFAULT 'unknown'
        CHECK (status IN ('in_force', 'superseded', 'repealed', 'unknown')),
    file_sha256 text NOT NULL UNIQUE,
    storage_path text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    pipeline_status text NOT NULL DEFAULT 'fetched'
        CHECK (pipeline_status IN ('fetched', 'extracted', 'chunked', 'embedded', 'indexed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX documents_source_id_idx ON documents (source_id);
CREATE INDEX documents_status_idx ON documents (status);

-- Explicit supersession/amendment graph (PROJECT_SPEC.md §6): e.g.
-- "Circular 4/2024 supersedes 9/2022."
CREATE TABLE document_relations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    to_document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    relation text NOT NULL CHECK (relation IN ('supersedes', 'amends', 'refers_to')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_document_id <> to_document_id),
    UNIQUE (from_document_id, to_document_id, relation)
);

CREATE INDEX document_relations_from_document_id_idx ON document_relations (from_document_id);
CREATE INDEX document_relations_to_document_id_idx ON document_relations (to_document_id);

-- The retrieval unit. embedding is sized for BAAI/bge-m3 (1024 dimensions).
CREATE TABLE chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    section_ref text,
    page_start integer,
    page_end integer,
    content text NOT NULL,
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    embedding vector(1024),
    token_count integer NOT NULL,
    chunk_index integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX chunks_document_id_idx ON chunks (document_id);
CREATE INDEX chunks_content_tsv_gin_idx ON chunks USING gin (content_tsv);
CREATE INDEX chunks_embedding_hnsw_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- Per-document pipeline stage status, powering resumability (PROJECT_SPEC.md §4.2, §7).
CREATE TABLE ingestion_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    stage text NOT NULL
        CHECK (stage IN ('fetched', 'extracted', 'chunked', 'embedded', 'indexed', 'failed')),
    attempt_count integer NOT NULL DEFAULT 0,
    error_details jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ingestion_jobs_document_id_idx ON ingestion_jobs (document_id);
CREATE INDEX ingestion_jobs_stage_idx ON ingestion_jobs (stage);

CREATE TABLE api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash text NOT NULL UNIQUE,
    name text NOT NULL,
    scopes text[] NOT NULL DEFAULT '{}',
    rate_limit_per_min integer NOT NULL DEFAULT 60,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

-- One row per answered or refused question (PROJECT_SPEC.md §6, §10, §11).
-- confidence stores the raw top rerank score so thresholds can be
-- recalibrated against historical queries without re-running retrieval.
CREATE TABLE queries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id uuid REFERENCES api_keys (id),
    question text NOT NULL,
    retrieved_chunk_ids uuid[] NOT NULL DEFAULT '{}',
    confidence double precision,
    answered boolean NOT NULL DEFAULT false,
    latency_ms integer,
    token_cost numeric(10, 6),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX queries_api_key_id_idx ON queries (api_key_id);
CREATE INDEX queries_created_at_idx ON queries (created_at);

-- migrate:down

DROP TABLE IF EXISTS queries;
DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS ingestion_jobs;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS document_relations;
DROP TABLE IF EXISTS documents;
DROP EXTENSION IF EXISTS vector;
