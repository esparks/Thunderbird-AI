# Thunderbird-AI

A local, always-on assistant that **reads your email** (read-only) and keeps your
**Google Calendar** up to date. It uses a local **Ollama** model to pull three
kinds of items out of incoming mail — **doctor appointments, bills, and
vacations** — creates the matching calendar events with reminders, and posts a
note to **Discord** whenever it does.

It never sends, moves, or deletes email. Your existing mail filters keep doing
their job; this only reads.

- **Bills** → Bills calendar, notice to `#finances`
- **Appointments + vacations** → Personal calendar, notice to `#personal`
- Low-confidence extractions are still added, but the Discord notice is flagged
  ⚠️ so you can double-check.

## How it works

```
IMAP (read-only)  ->  Ollama (extract JSON)  ->  classify + dedupe (SQLite)
                                                      |
                        +-----------------------------+
                        v                             v
              Google Calendar create           Discord webhook notify
```

## Quick start

See **[docs/SETUP.md](docs/SETUP.md)** for the full walk-through. Short version:

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.env config.env
REM edit config.env  (this is where you enter the mailbox password + webhooks)
run.bat --check          REM validate config
run.bat --once           REM one test pass (set DRY_RUN=true in config first)
run.bat                  REM run the loop
```

Design notes and decisions live in **[docs/PLAN.md](docs/PLAN.md)**.
