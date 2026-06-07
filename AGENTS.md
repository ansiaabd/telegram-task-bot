# TaskBot Telegram — Session State

## Project
Telegram-бот для управления задачами с ролями (админ, модератор, пользователь), подтверждением выполнения и уведомлениями.

## Current State (8 June 2026)
- Bot running with PID from start.sh
- All implemented features are stable

## How to start a new session

1. Read this file first (AGENTS.md)
2. Check if bot is running: `ps aux | grep "python main.py"`
3. If not running, start with: `bash start.sh` (или `python main.py &`)
4. Bot log is in bot.log in project root

## Structure

```
├── main.py              # Entry point
├── config.py            # .env config
├── bot/
│   ├── handlers.py      # All command/button handlers
│   ├── messages.py      # Message templates
│   └── keyboards.py     # Inline keyboards
├── db/
│   ├── schema.sql       # DDL (users: role column, tasks: created_by)
│   ├── crud.py          # DB operations
│   └── __init__.py      # SQLite connection (WAL mode)
├── scheduler/
│   └── tasks.py         # Overdue check via JobQueue (60s)
├── utils/
│   └── date_parser.py   # Russian date parser
├── .env                 # BOT_TOKEN, ADMIN_ID
├── tasks.db             # SQLite DB (created on first run)
└── docs/spec.md         # Tech spec
```

## Key files & line numbers (bot/handlers.py)
- `add_start:80` — entry point (inline format + conversation)
- `_ask_assignee:145` — shows user picker buttons
- `assignee_text:157` — text @username input
- `assignee_callback:165` — inline button user selection
- `add_title:183` — title input (also parses inline "title/desc/deadline")
- `add_description:210` — description input
- `_finish_task:228` — creates the task in DB
- `button_callback:380` — all inline button actions
- `_notify_approvers:250` — sends approval requests to admin + creator
- `get_handlers:530` — register all handlers

## Roles
- **ADMIN_ID** = 798479064 (from .env)
- Role stored in `users.role`: `'admin'`, `'moderator'`, `'user'` (default)
- `_get_role(user_id)` — helper, returns 'admin' for ADMIN_ID
- `_can_approve(user_id, task)` — checks admin or task creator

## Commands
| Command | Who | Description |
|---------|-----|-------------|
| /start | All | Register / greeting |
| /add | All | Create task (assignee first → title → desc → deadline) |
| /list | All | My tasks (admin sees all, mod sees assigned+created) |
| /list all | Admin | All tasks |
| /done <id> | All | Mark done (admins/mods approve own) |
| /delete <id> | All | Delete task |
| /overdue | All | Overdue tasks (role-filtered) |
| /pending | Admin+Mod | Tasks awaiting approval |
| /users | Admin | List users with roles |
| /removeuser <id> | Admin | Remove user |
| /promote <id> | Admin | Set moderator role |
| /demote <id> | Admin | Remove moderator role |
| /cancel | All | Cancel conversation |
| /help | All | Help |

## Inline (one-line) format
- `задача / title / deadline / @assignee`
- `задача / title / description / deadline / @assignee`
- `задача title / deadline / @assignee` (with space after "задача")
- Deadline can be in any position after title (scans all parts)
- Trigger words: "задача", "/add"

## Natural language
- «выполнено» / «сделано» / «готово» — mark task as done (if only 1 active task)

## Approval flow
1. Executor marks done → status = `pending_approval`
2. `_notify_approvers` sends to task creator AND admin
3. Creator or admin clicks approve/reject → status = `done` / `active`

## Conversation flow
1. ASSIGNEE: pick user (inline buttons) or type @username
2. TITLE: type title (or "title/desc/deadline" inline)
3. DESCRIPTION: type description (or "desc/deadline" inline)
4. DEADLINE: type deadline → task created

## Pending / postponed
- Voice message processing (speech-to-text) — not implemented yet
- Calendar sync (Google/Outlook) — not implemented

## Known issues
- If the bot crashes or gets killed, wait ~5 seconds before restarting (Telegram API conflict)
- After DB drop, all users must re-register via /start
- `/done` by executor always requires admin/moderator approval
