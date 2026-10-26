CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS ingestion_episodes (
    episode_id UUID PRIMARY KEY,
    episode_hash VARCHAR(64) UNIQUE NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    raw_transcript TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PROCESSING',
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS person_staging (
    uid UUID PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    email VARCHAR(255),
    phone VARCHAR(32),
    linkedin_url TEXT,
    github_handle VARCHAR(128),
    x_handle VARCHAR(128),
    current_org VARCHAR(255),
    "current_role" VARCHAR(255),
    alumni_orgs JSONB DEFAULT '[]'::jsonb,
    location_city VARCHAR(128),
    reachability_tier SMALLINT DEFAULT 2,
    trust_score FLOAT DEFAULT 50.0,
    verified BOOLEAN DEFAULT FALSE,
    embedding vector(384),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_person_staging_email ON person_staging(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_person_staging_phone ON person_staging(phone) WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_person_staging_linkedin ON person_staging(linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_person_staging_embedding ON person_staging USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS hitl_evidence_cards (
    card_id UUID PRIMARY KEY,
    langgraph_thread_id VARCHAR(128) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    subject_a_uid UUID,
    subject_a_name VARCHAR(255) NOT NULL,
    subject_b_uid UUID,
    subject_b_name VARCHAR(255) NOT NULL,
    proposed_relation VARCHAR(64) NOT NULL,
    confidence_score FLOAT NOT NULL,
    evidence_summary TEXT NOT NULL,
    source_urls JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_hitl',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
