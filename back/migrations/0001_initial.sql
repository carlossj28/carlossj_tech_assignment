-- Grupo Sazon screening schema. One migration, three tables.
-- Applied on startup by db.init_db() (idempotent via IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS conversations (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source            TEXT        NOT NULL CHECK (source IN ('chat', 'voice')),
    -- Computed from extracted_fields on every answer, never by the model (ADR-017).
    screening_status  TEXT        NOT NULL DEFAULT 'pending'
                                  CHECK (screening_status IN ('pending', 'qualified', 'disqualified')),
    knockout_reason   TEXT        CHECK (knockout_reason IN ('no_license', 'out_of_service_area')),
    completed         BOOLEAN     NOT NULL DEFAULT false,  -- Rita closed; a new message reopens (ADR-028)
    candidate_name    TEXT,                    -- mirrored from extracted_fields for cheap listing
    extracted_fields  JSONB       NOT NULL DEFAULT '{}',  -- the "shared sheet" voice rehydrates
    summary           TEXT,
    nudge_count       INT         NOT NULL DEFAULT 0,     -- reminders in the current silence (ADR-026)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at  TIMESTAMPTZ NOT NULL DEFAULT now()  -- last candidate message; "inactive" derives from it
);

-- Append-only transcript. Rita's turn carries the tools it ran in tool_calls (audit only, ADR-025).
CREATE TABLE IF NOT EXISTS turns (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT        NOT NULL,       -- voice: approximate Whisper transcript
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

-- Recruiter inbox sorts by recent activity.
CREATE INDEX IF NOT EXISTS conversations_activity_idx ON conversations (last_activity_at DESC);

-- Scale notes (10K candidates/week ≈ 2-3 writes/s peak — the DB is NOT the
-- bottleneck; OpenAI latency/rate-limits are). Open doors, none needed yet:
--   · turns growth (~6M rows/yr): partition by month or archive cold rows.
--   · dashboard analytics: materialized view if COUNT/AVG gets slow.
--   · connection fan-out across API replicas: front with PgBouncer.
