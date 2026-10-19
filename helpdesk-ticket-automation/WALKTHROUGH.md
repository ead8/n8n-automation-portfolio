# Build Walkthrough — node by node

How the Helpdesk Ticket Automation works, explained so you can read and present it.
A webhook receives customer support tickets, the workflow validates and triages each
one, answers common questions automatically from an embedded knowledge base, and
escalates everything else to a human with an SLA deadline. Every ticket is logged.

> n8n note: `{{ ... }}` is an **expression** n8n evaluates at run time.
> `$env.VAR` reads an environment variable from the n8n process.
> `$('Node Name')` pulls the output of an earlier node — used here because HTTP
> Request nodes replace the item with their own response, so the record assembled
> earlier is re-attached downstream.

```
POST /webhook/helpdesk-ticket
  → Validate & Normalize → Valid ticket?
      → no  → Reject invalid ticket (400)
      → yes → Classify (rules-based triage) → Knowledge base lookup → Auto-resolvable?
          → yes → Compose auto-reply → Send customer reply (HTTP) → Assemble auto-reply record ─┐
          → no  → Compose escalation → Post to Slack (HTTP)      → Assemble escalation record ─┤
                                                                                               ├→ Write ticket record → Reply to customer (200)
```

**1. New ticket (webhook)** — POST `/helpdesk-ticket`, `responseMode: responseNode`.
Accepts `{name, email, subject, message, channel}`. The workflow itself controls the
HTTP response through the Respond nodes at the end.

**2. Validate & Normalize** (Code) — requires `name`, `email` (regex-validated),
`message`; defaults `channel` to `"web"`. Mints the ticket id
`TKT-YYYYMMDD-HHMMSS-xxxx` (4 random hex chars) and a lowercased `text` field
(`subject + " " + message`) that every downstream matcher reads. Unwraps the body
n8n nests under `$json.body`. Output: `{valid, errors[], ticket}`.

**3. Valid ticket?** (IF) — `valid == true` continues down the main lane; otherwise…

**3b. Reject invalid ticket** (Respond to Webhook) — HTTP 400
`{ok:false, errors:["email is required", …]}`. No ticket is created, nothing is
logged — fail fast at the edge.

**4. Classify (rules-based triage)** (Code) — deterministic keyword scoring, **not
AI** (there's a documented slot to swap in an LLM — see README). Categories:
`billing / technical / account / order / general`. Priority: `high` on urgent
keywords (outage, down, hacked, fraud, breach, "all users", "can't access", data
loss, security, urgent, asap) or billing + payment-failure phrases ("charged
twice", "unauthorized") or ≥2 frustration words on a technical ticket; `medium`
for technical/billing/order; else `low`. Emits `slaHours` (high→1, medium→8,
low→24) and an ISO `slaDeadline`. Output: `{category, priority, matchedKeywords[],
slaHours, slaDeadline}`.

**5. Knowledge base lookup** (Code) — 8 embedded articles (password reset, refund
policy, double charge, plan upgrade, API 401/rate-limit, invite team member, export
data, contact human support), each with `keywords[]` and a genuinely useful 2–4
sentence answer. Score = keyword hits in the ticket text; `kbHit` when score ≥ 2.
Output: `{kbHit, article|null, score}`.

**6. Auto-resolvable?** (IF) — `kb.kbHit == true AND priority != "high"` →
auto-reply lane; anything else (no KB answer, or urgent) → escalation lane. Note
the guard: a high-priority ticket with a KB match still goes to a human.

**7a. Compose auto-reply** (Code) — builds `{to, subject, body}`: personalised
greeting with the customer's name, ticket id, the KB article body + link, "reply
to reopen this ticket", footer. Also builds the `record` object carried forward
for logging.

**7b. Send customer reply** (HTTP Request) — POSTs the email payload to
`{{ $env.OUTBOUND_EMAIL_URL }}`. In production this points at a real mail API
(Resend/Postmark/SendGrid) or an n8n Gmail node — one env var to swap.

**8a. Assemble auto-reply record** (Code) — merges the composed record with the
HTTP result via `$('Compose auto-reply')` → `{record, ticketId,
status:"auto_resolved", …, message}`.

**7c. Compose escalation** (Code) — builds the Slack alert: ticket id, category,
priority, SLA deadline, customer name/email, 200-char summary, suggested queue
(`billing→billing-queue`, `technical→eng-oncall`, `account→support-tier1`,
`order→fulfillment`, `general→support-tier1`), and whether a KB article was
attempted.

**7d. Post to Slack** (HTTP Request) — POSTs to `{{ $env.SLACK_WEBHOOK_URL }}`.
In production: a real Slack incoming webhook URL.

**8b. Assemble escalation record** (Code) — same merge pattern →
`status:"escalated_to_human"`.

**9. Write ticket record** (Code, `fs`) — writes the full record (ticket +
classification + KB result + outcome) to
`$HELPDESK_DATA_DIR/ticket-<id>.json`. One JSON file per ticket: a simple,
auditable trail. (Production would swap this node for Postgres/Supabase.)

**10. Reply to customer** (Respond to Webhook) — HTTP 200
`{ok:true, ticketId, status, category, priority, slaDeadline, message}` — e.g.
`"Ticket TKT-… was resolved automatically — the answer has been emailed to you."`
or `"…has been escalated to our support team."`

## The two paths, concretely

- *"I forgot my password, how do I reset it?"* → account/low, KB hit →
  `auto_resolved`, customer gets the reset steps by email.
- *"I was charged twice on my card this morning"* → billing/high, KB hit but
  priority is high → `escalated_to_human`, Slack alert to `billing-queue` with a
  1-hour SLA.
- *"The dashboard is down for our whole team"* → technical/high, no KB hit →
  `escalated_to_human`, Slack alert to `eng-oncall`.
- *Missing email field* → 400, `{"ok":false,"errors":["email is required"]}`.

## Test evidence

`TEST_REPORT.md` has the full matrix: 7 scenarios, 42 individual checks, all
passing against a real n8n 2.43.8 instance. `test/` contains the mock outbound
server and the test runner so the whole suite is reproducible.
