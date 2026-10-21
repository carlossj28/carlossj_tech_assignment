-- Grupo Sazon screening schema. One migration, three tables.
-- Applied on startup by db.init_db() (idempotent via IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS conversations (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source                  TEXT        NOT NULL CHECK (source IN ('chat', 'voice')),
    status                  TEXT        NOT NULL DEFAULT 'in_progress'
                                        CHECK (status IN ('in_progress', 'closed')),
    outcome                 TEXT        CHECK (outcome IN ('qualified', 'disqualified', 'review')),
    qualified               BOOLEAN,                 -- sealed by Python, not the model
    disqualification_reason TEXT        CHECK (disqualification_reason IN ('no_license', 'out_of_service_area')),
    closed_by               TEXT        CHECK (closed_by IN ('confirm', 'hangup', 'idle')),
    candidate_name          TEXT,                    -- mirrored from extracted_fields for cheap listing
    extracted_fields        JSONB       NOT NULL DEFAULT '{}',  -- the "shared sheet" voice rehydrates
    summary                 TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at                TIMESTAMPTZ
);

-- Append-only transcript. One row per message; tool_calls holds the tool trace.
CREATE TABLE IF NOT EXISTS turns (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content         TEXT,                            -- voice: approximate Whisper transcript
    tool_calls      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS turns_conversation_idx ON turns (conversation_id, id);

-- Recruiter dashboard auth.
CREATE TABLE IF NOT EXISTS recruiters (
    id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,              -- Argon2
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Recruiter inbox sorts by recent activity; index the common filters.
CREATE INDEX IF NOT EXISTS conversations_activity_idx
    ON conversations (COALESCE(ended_at, created_at) DESC);

-- Scale notes (10K candidates/week ≈ 2-3 writes/s peak — the DB is NOT the
-- bottleneck; OpenAI latency/rate-limits are). Open doors, none needed yet:
--   · turns growth (~6M rows/yr): partition by month or archive cold rows.
--   · dashboard analytics: materialized view if COUNT/AVG gets slow.
--   · connection fan-out across API replicas: front with PgBouncer.
