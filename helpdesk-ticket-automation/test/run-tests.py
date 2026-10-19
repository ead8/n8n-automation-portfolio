#!/usr/bin/env python3
"""End-to-end tests for the Helpdesk Ticket Automation n8n workflow."""
import json, os, sys, time, urllib.request

WEBHOOK = 'http://localhost:5678/webhook/helpdesk-ticket'
DATA_DIR = '/tmp/helpdesk-data'
CAPTURES = os.path.join(DATA_DIR, 'captures.jsonl')

def post(ticket):
    req = urllib.request.Request(WEBHOOK, data=json.dumps(ticket).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def get_captures():
    if not os.path.exists(CAPTURES): return []
    return [json.loads(l) for l in open(CAPTURES) if l.strip()]

def clear_captures():
    open(CAPTURES, 'w').close()

def ticket_files():
    return [f for f in os.listdir(DATA_DIR) if f.startswith('ticket-TKT-')] if os.path.exists(DATA_DIR) else []

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" — {detail}" if detail and not cond else ""))

def run_case(num, ticket, expect):
    clear_captures()
    before = set(ticket_files())
    try:
        status, resp = post(ticket)
    except Exception as e:
        check(f"Test {num}", False, f"request failed: {e}")
        return None
    caps = get_captures()
    emails = [c for c in caps if c['endpoint'] == '/mock/email']
    slacks = [c for c in caps if c['endpoint'] == '/mock/slack']
    new_files = set(ticket_files()) - before

    tid = resp.get('ticketId', '')
    if expect.get('http') == 400:
        check(f"Test {num} (400)", status == 400 and resp.get('ok') is False and resp.get('errors'),
              f"got {status} {resp}")
        return None
    check(f"Test {num} status={expect['status']}", resp.get('status') == expect['status'], str(resp))
    check(f"Test {num} category={expect['category']}", resp.get('category') == expect['category'], str(resp.get('category')))
    check(f"Test {num} priority={expect['priority']}", resp.get('priority') == expect['priority'], str(resp.get('priority')))
    check(f"Test {num} email_sent={expect['email']}", (len(emails) > 0) == expect['email'],
          f"emails={len(emails)}")
    check(f"Test {num} slack_sent={expect['slack']}", (len(slacks) > 0) == expect['slack'],
          f"slacks={len(slacks)}")
    check(f"Test {num} ticket_file", len(new_files) == 1, f"new files={new_files}")
    if expect.get('email_contains'):
        body = emails[0]['body'].get('body', '') if emails else ''
        check(f"Test {num} email_has_kb", expect['email_contains'].lower() in body.lower(), "kb text missing")
    if expect.get('slack_has'):
        txt = json.dumps(slacks[0]['body']) if slacks else ''
        check(f"Test {num} slack_has_fields", all(k in txt for k in expect['slack_has']), "slack fields missing")
    return tid

print("=== Helpdesk Ticket Automation E2E Tests ===\n")

# 1. Password reset -> auto_resolved
run_case(1, {"name":"Alice","email":"alice@example.com","subject":"Password reset",
    "message":"I forgot my password, how do I reset it?"},
    {'status':'auto_resolved','category':'account','priority':'low','email':True,'slack':False,
     'email_contains':'Forgot password'})

# 2. Double charge -> escalated billing/high
run_case(2, {"name":"Bob","email":"bob@example.com","subject":"Billing issue",
    "message":"I was charged twice on my card this morning, this is unauthorized!"},
    {'status':'escalated_to_human','category':'billing','priority':'high','email':False,'slack':True,
     'slack_has':['ticketId','slaDeadline']})

# 3. Outage -> escalated technical/high
run_case(3, {"name":"Carol","email":"carol@example.com","subject":"System down",
    "message":"The dashboard is down for our whole team, nobody can log in. This is urgent!"},
    {'status':'escalated_to_human','category':'technical','priority':'high','email':False,'slack':True,
     'slack_has':['ticketId','eng-oncall']})

# 4. Invite teammate -> auto_resolved with KB
run_case(4, {"name":"Dave","email":"dave@example.com","subject":"Team invite",
    "message":"How do I invite a teammate to my workspace?"},
    {'status':'auto_resolved','category':'account','priority':'low','email':True,'slack':False,
     'email_contains':'Invite members'})

# 5. Angry scam complaint -> escalated (no KB hit)
run_case(5, {"name":"Eve","email":"eve@example.com","subject":"Terrible service",
    "message":"This is a scam, I'm furious, get me a human NOW!"},
    {'status':'escalated_to_human','category':'general','priority':'high','email':False,'slack':True})

# 6. Missing email -> 400
run_case(6, {"name":"Frank","subject":"No email","message":"I have no email field"},
    {'http':400})

# 7. Refund policy -> auto_resolved with refund article
run_case(7, {"name":"Grace","email":"grace@example.com","subject":"Refund question",
    "message":"What's your refund policy if I cancel?"},
    {'status':'auto_resolved','category':'billing','priority':'medium','email':True,'slack':False,
     'email_contains':'30-day'})

print(f"\n=== {sum(1 for _,p,_ in results if p)}/{len(results)} checks passed ===")
sys.exit(0 if all(p for _,p,_ in results) else 1)
