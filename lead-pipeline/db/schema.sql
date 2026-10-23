-- Lead Pipeline schema (Postgres)
-- Used by: lead-pipeline-main, lead-pipeline-booking, lead-pipeline-reminder, error-handler
-- Apply once: psql "$DATABASE_URL" -f db/schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------- leads
CREATE TABLE IF NOT EXISTS leads (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key text UNIQUE NOT NULL,
  name            text NOT NULL,
  email           text NOT NULL,
  phone           text NOT NULL,              -- E.164, e.g. +251911234567
  status          text NOT NULL DEFAULT 'NEW',
  -- NEW -> CONTACTED -> BOOKED -> REMINDED, plus CANCELLED
  wa_message_id   text,
  event_id        text,                       -- Google Calendar event id
  meeting_start   timestamptz,
  timezone        text NOT NULL DEFAULT 'Africa/Addis_Ababa',
  reminder_sent   boolean NOT NULL DEFAULT false,
  attempts        int NOT NULL DEFAULT 0,
  last_error      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads (phone);
CREATE INDEX IF NOT EXISTS idx_leads_status_meeting ON leads (status, meeting_start);
CREATE INDEX IF NOT EXISTS idx_leads_idempotency ON leads (idempotency_key);

-- ------------------------------------------------------- pipeline_events
-- Append-only audit log: lead.created, whatsapp.failed, conversation turns,
-- booking.*, reminder.*. The booking workflow also reads conversation turns
-- from here as its chat memory.
CREATE TABLE IF NOT EXISTS pipeline_events (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id    uuid REFERENCES leads (id) ON DELETE SET NULL,
  type       text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_lead ON pipeline_events (lead_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON pipeline_events (type, created_at);

-- ------------------------------------------------------- pipeline_errors
-- Written by the global error handler workflow for every failed execution.
CREATE TABLE IF NOT EXISTS pipeline_errors (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow     text,
  node         text,
  error        text,
  execution_id text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------ dead_letter
-- Steps that failed after all retries (e.g. the WhatsApp welcome send).
-- A human works this table: resolved flips to true once handled.
CREATE TABLE IF NOT EXISTS dead_letter (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id    uuid REFERENCES leads (id) ON DELETE SET NULL,
  step       text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved   boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_open ON dead_letter (resolved, created_at);

-- ------------------------------------------------------------- updated_at
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads;
CREATE TRIGGER trg_leads_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
