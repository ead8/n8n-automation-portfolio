#!/bin/bash
# End-to-end test runner for Helpdesk Ticket Automation
# Runs the Python test suite against the live n8n webhook
set -e
cd "$(dirname "$0")"
python3 run-tests.py
