# Live Test Report: Lead Pipeline Workflows

**Date:** 2026-10-23
**Verdict:** 25 cases, 147 assertions, **all PASS**, after fixing 8 real defects that structural validation could not see.
**Environment:** n8n 2.43.8 (the install in `~/workspace/n8n-helpdesk/n8n`), PostgreSQL 16.15 local, mock server on 127.0.0.1:3999, driver in `test-run/run-tests.js`.

## Why this run exists

The first review of these workflows only checked structure: valid JSON, real node types, connections that resolve. The user asked whether the workflows had actually been run, case by case, angle by angle. They had not. This run executes all four workflows for real, against a real Postgres, with Meta, OpenAI, Google Calendar, Gmail, and Slack replaced by a local mock server (`test-run/mock-server.js`) that records every call and can be told to fail on cue.

## Setup

- Postgres 16 installed locally. Role `leadtest`, database `lead_pipeline_test`, schema applied from the deliverable `db/schema.sql` (leads, pipeline_events, pipeline_errors, dead_letter).
- Test copies of the workflows live in `test-run/workflows/`, produced by `test-run/transform-copies.js`. Changes in the copies only: the placeholder Postgres credential points at the test database, the Meta Graph URL points at the mock, the OpenAI URL points at the mock, and in the booking and reminder copies the native Google Calendar and Gmail nodes are replaced by HTTP nodes calling the mock, keeping the same node names, wiring, error outputs, and the data fields downstream nodes read. The availability mock returns the `{ available, busy }` shape the workflow's interpreter prefers.
- n8n ran with a fresh user folder under `test-run/n8n-home`, env access for nodes enabled, test values for all API keys and URLs. Workflows were imported and published with the n8n CLI. Webhooks were driven at their production URLs. The reminder sweep was run on demand through the n8n REST API manual run endpoint (`triggerToStartFrom: Hourly Schedule`), signed in as a local test owner account.
- Every case asserts on four kinds of evidence: the webhook HTTP response, rows in Postgres, the mock server's call log, and the n8n execution records in SQLite. State (tables, mock log, scenario) is reset between cases.

## Results by case

### Main workflow: intake and WhatsApp welcome (45 assertions)

| Case | Result | Evidence |
|---|---|---|
| M1 valid lead | PASS | HTTP 200 `{status: "CONTACTED"}`, execution 5 success. Lead row CONTACTED with `wa_message_id = wamid.TEST1`. Meta called exactly once, template `lead_welcome_booking` with the BOOK_CALL button. `lead.created` event logged. |
| M2 same submission_id again | PASS | HTTP 200 `{duplicate: true}`, execution 6 success. Meta count still 1, still exactly 1 lead row. |
| M3 same phone, new submission_id | PASS | `duplicate: true` via the phone match. Meta count still 1, 1 lead row. |
| M4 missing phone | PASS | HTTP 400 `{ok: false, errors: ["phone is required"]}`. No lead row, one `lead.rejected` event, zero Meta calls. |
| M5 bad email | PASS | HTTP 400, no lead row, rejection logged. |
| M6 Meta returns 422 | PASS | HTTP 200 `{status: "FALLBACK_EMAIL_SENT"}`, execution 10 success (failure handled in-flow). Fallback email called once, Slack alert once, one dead_letter row, `whatsapp.failed` logged, lead `last_error` carries the Meta error body. |
| M7 Meta fails twice, then OK | PASS | HTTP 200 CONTACTED. Meta called exactly 3 times (two 500s, then success), lead CONTACTED with `wamid.TEST3`, no dead_letter row. |
| M8 Meta always 500 | PASS | Meta called exactly 3 times (maxTries), then dead_letter row, fallback email once, Slack alert once, `last_error` set. |

### Booking workflow: WhatsApp replies and calendar booking (73 assertions)

| Case | Result | Evidence |
|---|---|---|
| B1 BOOK_CALL button, then text reply with a free slot | PASS | Button step returns `asked_for_slot` with zero calendar calls. Text step returns `{status: "BOOKED", eventId: "evt_test_1"}`, executions success. Lead BOOKED, `meeting_start = 2026-10-27 07:00 UTC` for the requested Tue 10:00 EAT slot. One freebusy call, one event create, one read-back. Confirmation WhatsApp sent, email invite sent to the lead, `booking.created` logged. |
| B2 requested slot and all 3 alternatives busy | PASS | Four freebusy probes, zero creates, lead still CONTACTED. Alternatives WhatsApp lists the 3 slots (Tue 27 Oct 11:00, 12:00, 13:00). `booking.alternatives_offered` logged. |
| B3 read-back sabotage, event vanishes | PASS | Create once, read-back attempted, event gone from the calendar store. Response `fallback_link_sent`, Slack alert sent, snag WhatsApp with booking link sent, lead NOT booked, `booking.failed` logged. |
| B3b read-back sabotage, start time mutated | PASS | Response `race_recovered`. The mismatched event was deleted through the calendar API, Slack race alert sent, alternatives message sent to the lead by name, lead NOT booked. |
| B4 CANCEL payload on a booked lead | PASS | Lead CANCELLED, the calendar event deleted through the API (mock store empty), cancellation ack sent on WhatsApp with the lead's name. |
| B5 wrong signature header | PASS | HTTP 403 `{error: "invalid signature"}`. Lead unchanged, no conversation turn logged, zero outbound calls. |
| B6 LLM returns a null slot | PASS | Response `asked_for_slot`, zero calendar calls of any kind, booking-link WhatsApp sent, `booking.slot_rejected` logged. |
| B7 calendar outage on availability | PASS | Response `fallback_link_sent`. Snag WhatsApp with booking link, one Slack alert, `booking.failed` logged, lead still CONTACTED. |
| B8 RESCHEDULE on a booked lead, LLM supplies a new slot | PASS | Old event deleted through the calendar API, new event created and read back, lead BOOKED with the new event_id, `meeting_start` moved to 2026-10-29 11:00 UTC, confirmation sent. |
| B8b bare RESCHEDULE tap, LLM returns no slot | PASS | Response `asked_for_slot`. Slot options message with booking link sent, no calendar delete, the existing booking is left fully intact. |

### Reminder workflow: day-before sweep (22 assertions)

Sweeps run through the REST manual run endpoint. Executions 54 to 58 in the final run.

| Case | Result | Evidence |
|---|---|---|
| R1 meeting in 24h, event exists | PASS | `meeting_reminder` template sent exactly once. Lead `reminder_sent = true`, status REMINDED. `reminder.sent` logged with `late = false`. Sweep summary posted to Slack: "1 reminders sent (0 late catch ups), 0 meetings found cancelled". |
| R2 event deleted from calendar | PASS | Lead CANCELLED, no reminder sent, sales Slack note sent ("calendar event ... no longer exists. Lead marked CANCELLED"), `reminder.cancelled` logged. |
| R3 meeting in 10h, catch-up path | PASS | Reminder template sent once, lead REMINDED, `reminder.sent` logged with `late = true`, ops late-reminder Slack note sent. |
| R4 nothing due | PASS | Zero Meta sends, zero Slack calls (no summary), zero emails. Execution success. |
| R5 sweep run twice | PASS | First run sends the reminder; second run sends nothing new (Meta count unchanged). |

### Error workflow: global error handler (7 assertions)

| Case | Result | Evidence |
|---|---|---|
| E1 failing main execution triggers the handler automatically | PASS | A variant of the main workflow was published with a deliberately wrong Postgres password (test copy only). A webhook lead made execution 60 end in `error` (HTTP 500 "Error in workflow"). The error workflow fired on its own: execution 61, mode `error`, status success. `pipeline_errors` gained exactly one row naming the intake workflow and execution_id 60, matching the failed execution. Slack received: "n8n error in Lead Pipeline: Intake + WhatsApp Welcome at node Find Lead by Idempotency Key: password authentication failed ..." |

## Bugs found by live testing, and the fixes applied to the deliverables

Structural validation passed all four files while every one of these defects was live in them.

### Bug 1: webhook nodes shipped without a webhookId

Both webhook nodes (`Lead Form Webhook`, `WhatsApp Inbound Webhook`) had no `webhookId`. Imported through the CLI or API, n8n then registers a dynamic path (`<workflowId>/<node name>/<path>`) instead of the production URL, so `POST /webhook/lead-intake` returned 404. The editor heals this on save, which is why it went unnoticed.
**Fix:** added stable webhookIds (`lead-pipeline-lead-intake`, `lead-pipeline-whatsapp-inbound`) to both nodes in the deliverables. Registrations are now the clean paths, proven by every webhook case above.

### Bug 2: empty SELECT results silently stall the flows

In n8n 2.43.8 the Postgres node returns zero items for a SELECT with no rows (confirmed in the installed node source), and a node that receives no items never runs. Three flows stalled silently, with the execution still marked success:
- Main: `Find Lead by Idempotency Key` returns no rows for every brand-new lead, so `Assess Existing Lead` never ran and intake died after the lookup. The webhook answered with an empty body and no lead was created. Caught by the first smoke test.
- Booking: `Load Lead by Phone` and `Load Conversation` had the same exposure for unknown numbers and empty history.
- Reminder: `Find Due Reminders` returning no rows meant the catch-up sweep and the summary never ran at all. A quiet hour would have looked identical to a working sweep.
**Fix:** `alwaysOutputData: true` on those five nodes in the deliverables. The downstream Code nodes were already written to tolerate an empty row. For the reminder loops, two guard IF nodes (`Has Lead Row?`, `Has Lead Row? (Late)`) were added so the synthetic empty row completes the batch loop without touching the calendar or the database.

### Bug 3: context loss where a Postgres or HTTP node sits mid-chain (6 nodes)

Postgres and HTTP nodes replace the item with their own result; they do not pass the incoming fields through. Several nodes read fields from `$json` or `$input` that an upstream database or HTTP node had already replaced, so in production they would have read `undefined`:
- Main, `Send WhatsApp Template`: body built from `$json.phone` and `$json.name`, but its input is the `Log Event` Postgres node, whose output is `{success: true}`. The send failed with "The value in the JSON Body field is not valid JSON" and every welcome message fell back to email. **This meant the pipeline's headline feature, the instant WhatsApp reply, never sent at all.**
- Booking, `Compose Cancel Ack`: read the lead's name and phone from the `Mark Cancelled` update result (`{id, status}`), so the ack could never be addressed or sent.
- Booking, `Compose Confirmation`: read everything from the `Log Booked` insert result (`{success: true}`), so the booking confirmation could never send and the invite email behind it never ran.
- Booking, `Compose Race Alternatives` and `Compose Snag Message`: read the lead context from a Slack webhook response.
- Booking, `Alert Ops Booking`: built its alert text from the `Log Booking Failure` insert result, so the alert would have said "lead undefined (undefined): undefined".
**Fix:** each of the six now reads the context from the node that actually produced it (for example `$('Merge Lead Context')`, `$('Attach Lead')`, `$('Verify Read-back')`, `$('Booking Failed Handler')`), the same explicit-reference pattern the rest of the workflows already use. B1, B3, B3b, B4, and B7 prove the repaired paths end to end.

### Bug 4: the sweep summary could never fire

`Any Activity?` in the reminder workflow compared `$json.total` with a numeric `largerEqual 1` condition. In this n8n build that comparison evaluates to false even when total is 1, reproduced in isolation with a two-node experiment (total 1 routed to the false branch; the same input with a boolean condition routed true). The counts were computed correctly and then thrown away, so the Slack summary was never posted.
**Fix:** the condition now uses the boolean pattern used by every other IF in the system: `={{ $json.total >= 1 }}`. R1 proves the summary now posts; R4 proves it stays silent when nothing happened.

### Bug 5: cancel did not delete the calendar event

DESCRIPTION.md promises "cancel sets status CANCELLED and deletes the event". The built cancel path only updated the database. The event stayed on the calendar, and only the reminder sweep's status filter prevented a stale reminder.
**Fix:** added a guarded `Delete Cancelled Event` step to the cancel branch (`Cancel Has Event?` IF plus the calendar delete, errors tolerated). B4 proves the event is now deleted through the calendar API.

## Observations (behavior verified, not counted as defects)

- On a non-retryable Meta error (422, bad template or number), the send node still burns all 3 retries, about 10 seconds, before the fallback path runs (M6 evidence: Meta count 3). The fallback outcome is correct; the delay is a tuning choice worth knowing about.
- Reschedule semantics, stated plainly: a bare RESCHEDULE tap does not delete anything; it asks the lead for a new time (B8b). The old event is deleted at the moment the replacement booking is created (B8). No window exists where the lead has a confirmation for an event that is not on the calendar, because deletion happens after the new slot passes availability.
- Postgres `count(*)` reaches the summary Code node as a string in this stack; the node already coerces with `Number()`, verified working in R1.
- The error handler wiring is a deployment step: the deliverable cannot hardcode `settings.errorWorkflow`, because the handler's workflow ID is assigned at import. In the test copy the setting was pointed at the handler before the failing run, and E1 proves the automatic trigger works once it is set. Anyone deploying these files must set that one setting, or failures will have no safety net.

## What was not exercised

- Real Meta, Google, and OpenAI services. By design, everything external was the local mock; the workflows' requests were captured and answered with realistic payloads, including Meta's error shape.
- The native Google Calendar and Gmail nodes themselves. In the test copies they are HTTP stand-ins against the mock (the deliverables keep the native nodes). Their output shapes were mirrored from what the workflow's interpreter and read-back check consume, and every downstream behavior (availability, create, read-back, delete, invite) was exercised through those shapes.
- The schedule trigger firing on its own hour. Sweeps were started through the REST manual run endpoint with the schedule node as the start trigger. The trigger's registration was verified at publish time.
- Load, concurrency races between two simultaneous leads, and token expiry against the real providers.

## Final state

- Deliverables in `workflows/` carry all fixes above. `tests/validate.js`: ALL PASS (main 27 nodes, booking 77 nodes, reminder 34 nodes, error handler 5 nodes).
- Em dash scan and secret scan over the deliverables: clean. No credentials in any deliverable file; the workflows reference env var names and placeholder credential names only.
- Test scaffolding (mock server, driver, copies, run logs) is in `test-run/`. The local n8n instance, mock server, and Postgres used for this run were stopped after testing.
