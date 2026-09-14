# Thunderbird-AI — Planning & Design

_Last updated: 2026-09-14_

A personal, always-on assistant that reads email and maintains the calendar.
This document is the reference for design decisions and setup details so any
future session can pick up where we left off.

---

## 1. Goal

Run a local, free, 24/7 agent on a Mini PC that **reads incoming email**,
extracts **Doctor appointments, bills, and vacations**, and maintains **Google
Calendar** events + reminders accordingly. It **notifies** the user (via an
existing Discord setup) whenever it creates or edits a calendar event.

**Explicitly out of scope:** the agent does NOT organize, move, delete, or
otherwise act on email (existing mail filters already handle that). It only
*reads* mail. No task/knowledge-base features. No meetings (personal calendar
only: Dr. appointments, bills, vacations).

---

## 2. Chosen architecture — Standalone

The agent is fully self-contained on the Mini PC and free-running. It writes to
Google Calendar itself and posts notifications to Discord via webhooks. It does
**not** depend on the separate `hq-agent-org` Claude/Discord system being up,
and consumes no Claude usage.

```
              Win Element M9 · Windows 11 · N100 · 16GB · 24/7
  ┌──────────────────────────────────────────────────────────────┐
  │  Python service (Scheduled Task, restart-on-failure)           │
  │                                                                │
  │  [1] IMAP poll ─► [2] SQLite ─► [3] Ollama ─► [4] Classify     │
  │   nixins:143      seen-UIDs     llama3.2:3b    Dr appt / bill /│
  │   STARTTLS        + dedupe      JSON schema    vacation +      │
  │   all folders*                  extract        confidence     │
  │                                      │                          │
  │                                      ├──► [5a] Google Calendar   │
  │                                      │      • Personal: appts,   │
  │                                      │        vacations          │
  │                                      │      • Bills: bill dates  │
  │                                      │      (+ reminders)        │
  │                                      └──► [5b] Discord webhook    │
  │                                             notify on create/edit│
  └──────────────────────────────────────────────────────────────┘
  * all folders EXCEPT Trash, Junk/Spam, Archives (+ subfolders)
```

---

## 3. Hardware profile (the Mini PC)

| Spec | Value | Implication |
|---|---|---|
| Machine | Win Element M9 | — |
| OS | Windows 11 Pro (build 22631), 64-bit | Native Ollama build available |
| CPU | Intel N100, 4 cores / 4 threads | CPU-only inference; adequate for this small batch workload |
| RAM | 16 GB (15.7 usable) | Fits a small model + OS + agent |
| GPU | Intel UHD (integrated), no CUDA | No GPU acceleration — Ollama runs on CPU |

**Model choice:** start with `llama3.2:3b` (Q4, ~2 GB, fast on N100) using
Ollama **structured/JSON-schema output** for reliable field extraction.
Fallback to `qwen2.5:7b` (~4.7 GB, slower) if extraction accuracy is
insufficient. ~20 emails/day is a tiny, non-real-time workload.

---

## 4. Accounts & endpoints

- **Email (read-only, IMAP):** `dfw-r02.nixins.com`, port **143**, **STARTTLS**,
  normal password. Username `erich@erichsparks.com` (Nixihost). Read all folders
  **except** Trash, Junk/Spam, Archives (+ subfolders). Password lives only in a
  local config file on the Mini PC — never committed, never pasted into chat.
- **Calendar (read/write):** Google account **sparkserich@gmail.com**.
  - Appointments + vacations → **Personal** calendar (id `sparkserich@gmail.com`).
  - Bills → **Bills** calendar, id
    `869d4ec22cbd42a97a372fc0a2065bdf5a6d7e80d6185bf1c0054149ea94e03f@group.calendar.google.com`.
  - The standalone agent needs its own Google Cloud project + Calendar API +
    OAuth "desktop" credential, with a one-time browser sign-in on the Mini PC.
    NOTE: nothing to reuse — the Mini PC's existing Google Calendar access is via
    the claude.ai MCP connector (account-scoped), which a standalone Python
    service cannot call. A fresh `credentials.json`/`token.json` is required.
- **Notifications (Discord):** reuses the existing hq-agent-org Discord **bot**
  (investigation on the Mini PC confirmed a bot, not webhooks). Default
  `DISCORD_MODE=bot`; the service posts via the Discord REST API using the bot
  token from `C:\Users\erich\.claude\channels\discord\.env` (`DISCORD_BOT_TOKEN`).
  - Bills → `#finances` (channel id `1492035391711215676`)
  - Appointments + vacations → `#personal` (channel id `1492035190841671802`)
  - Bot token stored in local `config.env` only. A `webhook` mode is also
    available as an alternative.

---

## 5. Behavior decisions

- **Notification routing:** split by type (bills → #finances; appts/vacations →
  #personal).
- **Low-confidence handling:** still create the event, but flag the Discord
  notice with ⚠️ "please verify" so uncertain extractions get a human check.
- **Poll interval:** every ~15 minutes.
- **Reminder defaults (agent-created events):**
  - Bills: all-day on due date; reminders per the budget-sheet rule (below).
  - Appointments: timed; reminders 1 day and 2 hours before.
  - Vacations: multi-day all-day; reminder 3 days before start.

**Bill reminder rule (from the user's budget sheet):**
- Monthly bills: reminder on the funding-paycheck date, plus 48h and 24h before due.
- Annual bills: 1 week out, the funding paycheck date(s), plus 48h and 24h before.
- Renewals over $500 are funded from BOTH paychecks (currently Progressive only).

---

## 6. Relationship to `hq-agent-org`

`hq-agent-org` is a separate multi-agent system (Claude Code + Discord channel
plugin) running on a Windows box. Its **PA** agent already does Google Calendar +
vacations; its **Finances** agent already tracks bills. Its documented gap is
exactly **IMAP access to the self-hosted (Nixihost) mailbox** — which this
project fills. We deliberately chose **Standalone** (not feeding into that
system), so Thunderbird-AI owns its calendar writes and posts notifications to
the shared Discord for visibility.

---

## 7. Bills calendar — one-time setup (COMPLETED 2026-09-14)

Populated the **Bills** calendar with 17 recurring monthly bills from the user's
budget spreadsheet. All are all-day, monthly, color 11 (red), with 48h + 24h
popup reminders. (The "funding-paycheck-date" reminder was deferred — see Open
Items.)

| Day | Item | Amount | Source | Method |
|--:|---|--:|---|---|
| 1 | Rent | $1,250.00 | Bank ACH | Autopay |
| 5 | Fidelity card (7400) — payment DUE | (variable) | Bank ACH | Manual |
| 5 | Discover card (2531) — payment DUE | (variable) | Bank ACH | Manual |
| 7 | Instacart / Aldi order | $242.00 | Main (7400) | Manual |
| 8 | Amzn Digital | $18.35 | Main (7400) | Autopay |
| 10 | Namecheap | $18.68 | Rewards (2531) | Autopay |
| 10 | AGI Renters/Condo insurance | $9.17 | Rewards (2531) | Autopay |
| 10 | National Grid | $140.85 | Main (7400) | Autopay |
| 11 | Spectrum internet | $40.00 | Main (7400) | Autopay |
| 12 | 0% card payment | $279.30 | Bank ACH | Manual |
| 14 | Amazon Prime | $16.19 | Main (7400) | Autopay |
| 18 | Anthropic / Claude | $43.20 | Main (7400) | Autopay |
| 20 | Auto loan | $600.47 | Bank ACH | Autopay |
| 23 | TradingView | $16.15 | Main (7400) | Autopay |
| 25 | Nixihost | $50.95 | Main (7400) | Autopay |
| 26 | HBO Max | $2.99 | Main (7400) | Autopay |
| 30 | Rocket Money Premium | $3.24 | Both | Autopay |

**Cleanup done:** removed from the Personal calendar the 3 recurring bill series
(National Grid monthly; Discover 2531 on the 5th; Discover 2531 on the 7th) and
the upcoming Sewer bill (2026-09-18). Past one-off bill events were left in place
(user does not care about history).

**Annual / semi-annual bills — NOT yet created (need exact months):**
| Item | Cadence | Amount | Day | Notes |
|---|---|--:|--:|---|
| Progressive auto insurance | Semi-annual | ~$697 | 14 | $637 Sep / $756.99 Mar |
| RLI Insurance | Annual | $273.00 | 15 | Seen Sep |
| Mint Mobile | Annual | $200.81 | 26 | Prepaid; month unknown |
| ASI / Progressive | Annual | $150.30 | 13 | Sep & Aug |

---

## 8. Setup prerequisites (for the build phase)

1. **Ollama** installed on the Mini PC; pull `llama3.2:3b` (and optionally
   `qwen2.5:7b`).
2. **Google Cloud project** with Calendar API enabled + OAuth desktop
   credential; one-time browser auth on the Mini PC to mint a token.
3. **Discord incoming webhooks** created in `#finances` and `#personal`; URLs put
   in local config.
4. **IMAP password** for erich@erichsparks.com stored in local config on the Mini
   PC only.
5. **Windows Scheduled Task** to run the service at login with restart-on-failure.

---

## 9. Open items / TODO

- [x] Build the standalone Python agent (IMAP read → Ollama extract → Calendar
      write → Discord notify). Implemented in `thunderbird_ai/` — see
      `docs/SETUP.md`. Config/secrets in `config.env` (git-ignored). Reuses
      existing Google OAuth (`credentials.json`/`token.json`) and Discord
      webhooks. Ollama assumed already installed.
- [ ] Create the 4 annual/semi-annual bills once exact months are confirmed.
- [ ] Decide the precise "funding-paycheck-date" reminder mapping (esp. items
      funded by the prior month's paycheck: Rent, Anthropic) and add those
      reminders to the bill events (or let the agent manage them).
- [ ] Confirm the JSON extraction schema for the agent (fields: type, title,
      date/time, amount, payee, location, confidence).
- [ ] Define exact Discord notification message format.

---

## 10. Ideas for future tasks (brainstorm, not committed)

Bill/renewal detection with lead reminders; package/delivery tracking from
shipping emails; appointment detection with prep reminders; phishing/spam flags
(read-only, notify only); recurring weekly summary of upcoming bills &
appointments.

---

## Notes on session constraints (why some things can't be done from a chat session)

- No IMAP tool exists in the assistant session, and reading the Nixihost mailbox
  needs the password + code — that is the Mini PC agent's job, not a chat task.
- The Gmail connector (sparkserich@gmail.com) is not authorized for reading and,
  regardless, the bills are on erich@erichsparks.com (not in Gmail).
- The Google Calendar connector can create/edit/delete **events** but cannot
  create a **calendar** or **move** events between calendars — hence the Bills
  calendar was created by the user, and migration was done as create-on-Bills +
  delete-from-Personal.
