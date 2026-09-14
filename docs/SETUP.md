# Setup — Thunderbird-AI (Windows / Mini PC)

Do these once on the Mini PC. Everything runs locally; secrets stay in
`config.env` (git-ignored) and never leave the machine.

## 0. Prerequisites
- **Python 3.11+** installed and on PATH.
- **Ollama** installed (already done on this machine) and the model pulled:
  ```bat
  ollama pull llama3.2:3b
  ```

## 1. Install the app
From the project folder (the one containing `requirements.txt`):
```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## 2. Create your config
```bat
copy config.example.env config.env
```
Open `config.env` in a text editor and fill in the blanks:

### ▶ Where to put the mailbox password
In `config.env`, set:
```
IMAP_PASSWORD=your-mailbox-password-here
```
That's the only place the password lives. The IMAP host/port/username are
already filled in (`dfw-r02.nixins.com`, `143`, STARTTLS, `erich@erichsparks.com`).

### ▶ Discord (reuse your existing bot)
Default mode is `bot` — it posts as your existing hq-agent-org Discord bot, so
no new webhooks are needed. In `config.env`:
```
DISCORD_MODE=bot
DISCORD_BOT_TOKEN=<paste value of DISCORD_BOT_TOKEN>
DISCORD_CHANNEL_FINANCES=1492035391711215676   (already prefilled)
DISCORD_CHANNEL_PERSONAL=1492035190841671802   (already prefilled)
```
Get the token from `C:\Users\erich\.claude\channels\discord\.env` (the
`DISCORD_BOT_TOKEN` line) and paste the value here. The bot is already in the
server and allowlisted for both channels.

_Alternative:_ set `DISCORD_MODE=webhook` and fill `DISCORD_WEBHOOK_FINANCES` /
`DISCORD_WEBHOOK_PERSONAL` instead, if you'd rather use webhooks.

### ▶ Google Calendar (reuse your existing OAuth)
Put your existing OAuth **client** file in the project folder as
`credentials.json`. If you already have an authorized **token** from another
Google script, copy it in as `token.json` and you're done. If not, leave
`token.json` out — the first run will open a browser once to authorize, then
save `token.json` automatically.

The calendar IDs are already set:
- Personal (appointments + vacations): `sparkserich@gmail.com`
- Bills: the Bills calendar ID.

## 3. Validate
```bat
run.bat --check
```
Fix anything it reports (empty password, missing webhook, etc.).

### Authorize Google (one time)
```bat
run.bat --auth
```
Opens a browser; sign in as **sparkserich@gmail.com** and approve. Writes
`token.json`. (Requires sparkserich@gmail.com added as a Test user on the OAuth
consent screen, or it 403s.)

### Test Discord (optional)
```bat
run.bat --test-discord
```
Sends one message to #finances and one to #personal so you can confirm the bot
token + channel IDs work.

## 4. Test safely (no changes made)
Set `DRY_RUN=true` in `config.env`, then:
```bat
run.bat --once
```
It logs what it *would* create. Review `thunderbird_ai.log`. When happy, set
`DRY_RUN=false`.

> Tip: bump `LOOKBACK_DAYS` temporarily (e.g. 14) to test against recent mail,
> then set it back to `1`.

## 5. Run for real
```bat
run.bat --once     REM process current mail once
run.bat            REM run continuously, polling every 15 min
```

## 6. Auto-start 24/7 (Task Scheduler)
1. Open **Task Scheduler** → **Create Task**.
2. General: name `Thunderbird-AI`; "Run whether user is logged on or not".
3. Triggers: **At log on** (and/or **At startup**).
4. Actions: **Start a program** → Program/script: the full path to `run.bat`;
   "Start in": the project folder.
5. Settings: "If the task fails, restart every 1 minute, up to 3 times".

## Notes
- Read-only: mailboxes are opened `readonly=True`; no flags, moves, or deletes.
- Folders containing Trash/Junk/Spam/Archive are skipped.
- Dedupe: `thunderbird_ai_state.db` remembers processed emails and created
  events, so the same bill emailed twice won't double-book.
