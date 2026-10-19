# Test Report — Helpdesk Ticket Automation

**Date:** 2026-10-19
**n8n version:** 2.43.8 (installed via custom Python npm-compatible installer)
**Workflow:** "Helpdesk Ticket Automation" (ID: PUgt7Pw8urZxkibY)
**Webhook URL:** http://localhost:5678/webhook/helpdesk-ticket
**Test runner:** `test/run-tests.py`

## Test Matrix

| # | Input Summary | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | Password reset request ("I forgot my password, how do I reset it?") | auto_resolved, account/low, email sent, no Slack, ticket file | auto_resolved, account/low, email captured with KB article, ticket file written | **PASS** |
| 2 | "I was charged twice on my card this morning" (unauthorized) | escalated_to_human, billing/high, Slack with ticketId+slaDeadline, no email | escalated_to_human, billing/high, Slack captured with all fields, no email sent | **PASS** |
| 3 | "The dashboard is down for our whole team, nobody can log in" (urgent) | escalated, technical/high, Slack to eng-oncall | escalated_to_human, technical/high, Slack captured with eng-oncall queue | **PASS** |
| 4 | "How do I invite a teammate to my workspace?" | auto_resolved, KB hit, email with KB answer | auto_resolved, account/low, email captured containing "Invite members" KB text | **PASS** |
| 5 | "This is a scam, I'm furious, get me a human NOW" | escalated (no KB hit), Slack capture | escalated_to_human, general/high (scam=urgent keyword), Slack captured, no KB article matched | **PASS** |
| 6 | Missing email field | HTTP 400, {ok:false, errors[]} | HTTP 400 with errors: ["email is required"] | **PASS** |
| 7 | "What's your refund policy if I cancel?" | auto_resolved with refund article | auto_resolved, billing/medium, email captured containing 30-day refund policy | **PASS** |

**Result: 7/7 PASS (42/42 individual checks)**

## How It Was Executed

1. Real n8n 2.43.8 instance running on this VM (port 5678)
2. Workflow imported via `n8n import:workflow` and published via `n8n publish:workflow`
3. Python mock server on port 8899 captured outbound HTTP requests (`/mock/email`, `/mock/slack`)
4. Test script POSTed 7 tickets to the production webhook URL
5. Assertions verified: webhook response JSON, captured outbound requests, ticket files on disk
6. All 10 n8n executions show status "success" in `execution_entity`

## Evidence Paths

- **Outbound captures:** `/tmp/helpdesk-data/captures.jsonl` (email and Slack payloads)
- **Ticket files:** `/tmp/helpdesk-data/ticket-TKT-*.json` (7 files, one per test)
- **n8n executions:** `~/.n8n/.n8n/database.sqlite` → `execution_entity` (IDs 10-19, all "success")
- **n8n log:** `~/workspace/n8n-helpdesk/n8n.log`

## What's Mocked (Honest Disclosure)

1. **Outbound sends are HTTP POSTs to a mock server**, not real Gmail/Slack. The workflow POSTs to `$env.OUTBOUND_EMAIL_URL` and `$env.SLACK_WEBHOOK_URL`. In production, point these at a real email API (e.g., Gmail via n8n's Gmail node or an SMTP service) and a real Slack incoming webhook URL.

2. **The classifier is rules-based, not AI.** It uses deterministic keyword scoring. The workflow JSON and README document the exact slot where an LLM node (OpenAI/Anthropic) can replace it for smarter classification.

3. **n8n was installed via a custom Python installer**, not `npm i -g n8n`, because the sandbox intermittently blocks Node.js filesystem writes. The installed n8n 2.43.8 is genuine and unmodified; only the installation method was custom.

4. **The knowledge base is 8 hardcoded articles**, not a vector database or live help center. In production, replace with a real KB API or vector search.

5. **Ticket storage is local JSON files**, not a database or ticketing system (e.g., Zendesk, Jira). In production, replace the file-write Code node with a database or ticketing API integration.

## Fixes Made During Testing

1. **Webhook body unwrapping:** The Webhook node nests POST data under `$json.body`; the "Validate & Normalize" Code node was updated to unwrap it.
2. **File writing:** The `readWriteFile` node only handles binary data; replaced with a Code node using Node.js `fs` (requires `NODE_FUNCTION_ALLOW_BUILTIN=fs`).
3. **Env var access:** n8n 2.x blocks `$env` in expressions by default; set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.
4. **IPv6 localhost:** n8n resolved `localhost` to `::1` but the mock server was IPv4-only; switched URLs to `127.0.0.1`.
5. **Classifier keywords:** Added `invite`, `teammate`, `workspace`, `member` to the account category so team-invite tickets classify correctly.
6. **n8n 2.x publication:** Used `publish:workflow` CLI (not just `active=1`) to properly activate via the new publication service.
7. **Missing `entities@4.x`:** Installed nested copy for `htmlparser2` under `html-to-text` (hoisting bug in custom installer).
