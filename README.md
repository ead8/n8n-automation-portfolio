# n8n Automation Portfolio

Three production-style AI automation builds on **n8n** — each one a complete,
documented system: workflow JSONs, prompts, SQL, architecture diagrams, and a
node-by-node walkthrough.

## The builds

| Build | What it does | Stack |
|-------|--------------|-------|
| [ai-voice-front-desk](ai-voice-front-desk/) | AI voice receptionist: answers calls, qualifies callers, books appointments with round-robin + availability guard, transfers to a human; plus an outbound SDR dialer and a Vapi realtime upgrade | Twilio, n8n, OpenAI gpt-4o-mini, Google Calendar, Google Sheets, Vapi |
| [whatsapp-lead-qualifier](whatsapp-lead-qualifier/) | WhatsApp agent that runs a real BANT qualification over multiple turns, persists every fact to Postgres as it's learned, resumes dropped conversations days later, and routes hot leads to sales via Slack | n8n, OpenAI, WhatsApp Business Cloud API, Supabase Postgres, Slack |
| [crm-lead-engine](crm-lead-engine/) | Two-lane CRM engine on HubSpot: scheduled enrichment/scoring of existing contacts, plus an inbound email lead-capture lane that qualifies, temperature-routes, and auto-replies with guard-rails | n8n, OpenAI, HubSpot CRM API, Gmail, Slack |

Each folder has its own `README.md` (setup, architecture, results) and
`WALKTHROUGH.md` (every node explained). Workflow JSONs ship with credentials
stripped — import into n8n, add your own credentials, and run.

## Notes

- These are portfolio implementations of automation work delivered for clients;
  client-specific data, credentials, and branding have been removed.
- Workflow structures reference the public
  [n8n-automation-portfolio](https://github.com/patricksales-ai/n8n-automation-portfolio)
  project layouts.
