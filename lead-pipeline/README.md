# Lead Pipeline: Website Lead to Booked Call

An n8n system that takes a website lead from form submission to a booked calendar meeting, with a reminder the day before. Four workflows plus a Postgres schema.

## The workflows

- **Intake + WhatsApp Welcome** (`workflows/lead-pipeline-main.json`): form webhook, validation and normalization, idempotency dedupe, lead upsert, then an instant pre-approved WhatsApp template with a Book a Call quick-reply button. Send failures retry with backoff, then fall back to email, a dead-letter row, and an ops alert.
- **WhatsApp Replies + Calendar Booking** (`workflows/lead-pipeline-booking.json`): signature-verified inbound webhook, conversation state in Postgres, LLM slot extraction where the model proposes and code disposes, Google Calendar availability check, event create followed by a read-back verification, three alternatives when the slot is taken, and cancel and reschedule handling.
- **Day-Before Reminder Sweep** (`workflows/lead-pipeline-reminder.json`): hourly sweep that re-verifies the calendar event still exists before sending the reminder template, marks cancelled meetings honestly, catches up missed windows with a late flag, and stays idempotent across runs.
- **Global Error Handler** (`workflows/error-handler.json`): every failed execution in the three workflows above is logged to Postgres and posted to an ops Slack channel.

## Design and error handling

Error handling is the point of this build: duplicate submissions, invalid payloads, WhatsApp numbers that do not exist, Meta outages, double-booking races caught by read-back, calendar outages with a booking-link fallback, timezone-safe storage in UTC. The full design document is [DESCRIPTION.md](DESCRIPTION.md) and the diagram is [diagram/pipeline-diagram.png](diagram/pipeline-diagram.png).

## Testing

Live-tested end to end on n8n 2.43.8 against a real Postgres, with Meta, Google, OpenAI, and Slack replaced by a local mock server that records every call and fails on cue: **25 cases, 147 assertions, all passing.** Live testing caught 8 real defects that structural validation had missed, including one that silently prevented the WhatsApp welcome message from ever sending. Full evidence, case by case: [TEST_REPORT.md](TEST_REPORT.md). Structural validation of the workflow files: `node test/validate.js`.

## Setup

1. Apply `db/schema.sql` to a Postgres database.
2. Import the four workflow JSONs into n8n.
3. Add your own credentials (Postgres, Google Calendar, Gmail) and set the env vars the workflows reference: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `SLACK_OPS_WEBHOOK_URL`, `EMAIL_API_URL`, `OPENAI_API_KEY`.
4. In each of the three pipeline workflows, set the error workflow setting to the imported Global Error Handler.
5. Approve the two WhatsApp templates (`lead_welcome_booking`, `meeting_reminder`) in your Meta app, matching the button payloads the booking workflow expects (BOOK_CALL, CONFIRM, RESCHEDULE, CANCEL).
