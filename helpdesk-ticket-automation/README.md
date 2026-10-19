# Helpdesk Ticket Automation (n8n)

A production-style n8n workflow that receives customer support tickets via webhook,
validates and triages them, answers common questions automatically from an embedded
knowledge base, and escalates everything else to a human with an SLA deadline.

Built for a real demo: it runs end-to-end in n8n with zero external credentials —
outbound sends (customer email, Slack alerts) are plain HTTP POSTs that can be
pointed at real services in production.

## Architecture

```
                    ┌──────────────────────┐
  POST /webhook/    │  New ticket (webhook)│
  helpdesk-ticket ──▶│  responseMode:       │
  {name,email,      │  responseNode        │
   subject,message, └──────────┬───────────┘
   channel}                    │
                    ┌──────────▼───────────┐     ┌──────────────────────┐
                    │ Validate & Normalize │────▶│ Reject invalid ticket│ (400)
                    │ (Code)               │ no  │ (Respond to Webhook) │
                    └──────────┬───────────┘     └──────────────────────┘
                          yes  │
                    ┌──────────▼───────────────┐
                    │ Classify (rules-based    │  ← LLM upgrade slot
                    │ triage) (Code)           │    (see below)
                    └──────────┬───────────────┘
                               │
                    ┌──────────▼───────────────┐
                    │ Knowledge base lookup    │
                    │ (Code, 8 articles)       │
                    └──────────┬───────────────┘
                               │
                    ┌──────────▼───────────────┐
                    │ Auto-resolvable? (IF)    │  kbHit AND priority ≠ high
                    └──────┬───────────┬───────┘
                 yes │               │ no
        ┌────────────▼────┐   ┌──────▼─────────────┐
        │ Compose         │   │ Compose escalation │
        │ auto-reply      │   │ (Slack alert text, │
        │ (Code)          │   │ queue, SLA) (Code) │
        └────────┬────────┘   └──────┬─────────────┘
                 │                   │
        ┌────────▼────────┐   ┌──────▼─────────────┐
        │ Send customer   │   │ Post to Slack      │
        │ reply (HTTP     │   │ (HTTP POST)        │
        │ POST)           │   │                    │
        └────────┬────────┘   └──────┬─────────────┘
                 │                   │
        ┌────────▼────────┐   ┌──────▼─────────────┐
        │ Assemble auto-  │   │ Assemble escalation│
        │ reply record    │   │ record (Code)      │
        │ (Code)          │   │                    │
        └────────┬────────┘   └──────┬─────────────┘
                 └─────────┬─────────┘
                ┌──────────▼───────────┐
                │ Write ticket record  │  → $HELPDESK_DATA_DIR/ticket-<id>.json
                │ (Read/Write Files    │
                │  from Disk)          │
                └──────────┬───────────┘
                           │
                ┌──────────▼───────────┐
                │ Reply to customer    │  200 {ok, ticketId, status,
                │ (Respond to Webhook) │       category, priority,
                └──────────────────────┘       slaDeadline, message}
```

## Node-by-node walkthrough

| # | Node | Type | What it does |
|---|------|------|--------------|
| 1 | New ticket (webhook) | Webhook (POST `/helpdesk-ticket`, responseNode) | Entry point. `responseNode` means the workflow controls the HTTP response via the Respond nodes at the end. |
| 2 | Validate & Normalize | Code | Requires `name`, `email` (regex-validated), `message`. Defaults `channel` to `web`. Mints ticket id `TKT-YYYYMMDD-HHMMSS-xxxx` (4 random hex chars) and a lowercased `text` field for matching. |
| 3 | Valid ticket? | IF | `valid == true` continues; otherwise… |
| 3b | Reject invalid ticket | Respond to Webhook | HTTP 400 `{ok:false, errors:[...]}` — no ticket is created. |
| 4 | Classify (rules-based triage) | Code | **Deterministic keyword scoring, not AI.** Categories: billing / technical / account / order / general. Priority: `high` on urgent keywords (outage, down, hacked, fraud, breach, "all users", "can't access", data loss, security, urgent, asap, scam), billing + payment-failure phrases ("charged twice", "unauthorized"…), or ≥2 frustration words + technical category; `medium` for technical/billing/order; else `low`. SLA: high→1h, medium→8h, low→24h, emitted as an ISO `slaDeadline`. |
| 5 | Knowledge base lookup | Code | 8 embedded articles (password reset, refund policy, double charge, upgrade plan, API 401/rate-limit, invite team, export data, human support). Each has keywords + a genuinely useful 2–4 sentence answer. Score = keyword hits in ticket text; `kbHit` when score ≥ 2. |
| 6 | Auto-resolvable? | IF | `kb.kbHit == true AND priority != "high"` → auto-reply; otherwise escalation. |
| 7a | Compose auto-reply | Code | Builds `{to, subject, body}` — personalised greeting, ticket id, the KB article body + link, "reply to reopen", footer — plus a `record` object carried forward. |
| 7b | Send customer reply | HTTP Request | POSTs the email payload to `$env.OUTBOUND_EMAIL_URL`. In production: point at a mail API (e.g. Resend/Postmark/Gmail API) or an n8n Gmail node. |
| 8a | Assemble auto-reply record | Code | Merges the composed record + HTTP result → `{record, ticketId, status:"auto_resolved", …, message}`. Uses `$('Compose auto-reply')` to reference the earlier node output (HTTP nodes replace items with their response). |
| 7c | Compose escalation | Code | Builds a Slack message with ticket id, category, priority, SLA deadline, customer, summary, suggested queue (`billing→billing-queue`, `technical→eng-oncall`, `account→support-tier1`, `order→fulfillment`, `general→support-tier1`), and whether a KB article was attempted. |
| 7d | Post to Slack | HTTP Request | POSTs to `$env.SLACK_WEBHOOK_URL`. In production: a real Slack incoming webhook URL. |
| 8b | Assemble escalation record | Code | Same merge pattern → `status:"escalated_to_human"`. |
| 9 | Write ticket record | Read/Write Files from Disk | Writes the full record (ticket + classification + KB result + outcome) to `$HELPDESK_DATA_DIR/ticket-<id>.json`. |
| 10 | Reply to customer | Respond to Webhook | HTTP 200 `{ok:true, ticketId, status, category, priority, slaDeadline, message}`. |

Sticky notes on the canvas document sections 1–5 and call out the honesty points below.

## Environment variables

| Variable | Purpose | Test value | Production value |
|----------|---------|------------|------------------|
| `OUTBOUND_EMAIL_URL` | Where auto-reply emails are POSTed | `http://localhost:8899/mock/email` | Your mail API endpoint (Resend, Postmark, SendGrid, or an n8n Gmail node) |
| `SLACK_WEBHOOK_URL` | Where escalation alerts are POSTed | `http://localhost:8899/mock/slack` | A real Slack incoming webhook URL |
| `HELPDESK_DATA_DIR` | Where ticket JSON files are written | `/tmp/helpdesk-data` | A persistent directory / S3 / database |

n8n exposes these to expressions as `$env.VAR_NAME`.

## Import steps

1. Install n8n: `npm i -g n8n`
2. `n8n import:workflow --input=helpdesk-ticket-automation.json` → note the workflow id
3. Activate: `n8n update:workflow --id=<id> --active=true`
   (fallback: `sqlite3 ~/.n8n/database.sqlite "UPDATE workflow_entity SET active=1 WHERE id='<id>';"` then restart n8n)
4. Start: `HELPDESK_DATA_DIR=/tmp/helpdesk-data OUTBOUND_EMAIL_URL=… SLACK_WEBHOOK_URL=… N8N_PORT=5678 n8n start`
5. POST a ticket: `curl -X POST http://localhost:5678/webhook/helpdesk-ticket -H 'Content-Type: application/json' -d '{"name":"Sara","email":"sara@example.com","subject":"Password reset","message":"I forgot my password, how do I reset it?"}'`

## LLM upgrade slot

Node 4 ("Classify (rules-based triage)") is the documented swap point. In production,
replace it with an n8n **AI Agent** node (OpenAI/Anthropic credentials) with a structured-output
parser returning `{ category, priority }`, keeping the same output contract
(`category`, `priority`, `matchedKeywords`, `slaHours`, `slaDeadline`). Everything
downstream (KB routing, queues, SLA) works unchanged.

## Honest limitations

- The classifier is **rules-based keyword scoring, not AI/ML** — it's transparent and
  deterministic, but it won't understand paraphrase ("I can't get into my account"
  matches via "log in"/"password" keywords; truly novel phrasing may fall to `general`).
- Outbound sends are **plain HTTP POSTs** — the test rig uses a mock server that logs
  payloads. Real delivery needs real endpoints (see table above).
- Ticket storage is **one JSON file per ticket** — fine for a demo and audit trail;
  production would use Postgres/Supabase (swap node 9).
- KB is 8 static articles — production would search a real help-center index.
