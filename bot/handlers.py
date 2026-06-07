import re
from telegram import Update
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

from db.crud import (
    add_task, list_tasks, get_task, update_task_status, delete_task,
    list_overdue, list_pending_approval, register_user, get_user_by_username,
    get_user, list_users, delete_user,
)
from bot.messages import (
    HELP_TEXT, TASK_ADDED, TASK_DONE, TASK_NOT_FOUND, TASK_DELETED,
    NO_TASKS, INVALID_ID, NO_OVERDUE, INVALID_DATE,
    ASK_TITLE, ASK_DESCRIPTION, ASK_DEADLINE, ASK_ASSIGNEE,
    CANCELLED, SKIPPED_DESC, REGISTERED,
    DONE_REQUESTED, DONE_APPROVED, DONE_REJECTED, DONE_SENT_TO_ADMIN,
    NO_PENDING, NO_USERS, USER_REMOVED, USER_REMOVE_DENIED, USER_NOT_FOUND, ADMIN_ONLY,
)
from bot.keyboards import task_actions_keyboard, approval_keyboard
from utils.date_parser import parse_deadline, format_datetime_ru
from config import ADMIN_ID

TITLE, DESCRIPTION, DEADLINE, ASSIGNEE = range(4)


# ── Start / Registration ─────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username or "", user.full_name or user.first_name)
    await update.message.reply_text(
        REGISTERED.format(name=user.full_name or user.first_name)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


# ── Add task (inline + conversation) ─────────────────────

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*", text)]
    if parts[0].lower().lstrip("/") in ("задача", "add"):
        parts = parts[1:]

    if len(parts) >= 3:
        title = parts[0]
        candidate_deadline = parse_deadline(parts[1])
        if candidate_deadline:
            deadline = candidate_deadline
            assignee_raw = parts[2]
            description = " / ".join(parts[3:]) if len(parts) > 3 else ""
        else:
            description = parts[1]
            deadline = parse_deadline(parts[2])
            if not deadline:
                await update.message.reply_text(INVALID_DATE)
                return ConversationHandler.END
            assignee_raw = " / ".join(parts[3:]) if len(parts) > 3 else ""

        assignee_id = None
        user_data = get_user_by_username(assignee_raw)
        if user_data:
            assignee_id = user_data["user_id"]

        task_id = add_task(title, assignee_raw, deadline, description, assignee_id)
        desc_text = f"📋 {description}" if description else ""
        await update.message.reply_text(
            TASK_ADDED.format(id=task_id, title=title, deadline=format_datetime_ru(deadline), assignee=assignee_raw, description=desc_text),
            reply_markup=task_actions_keyboard(task_id),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(ASK_TITLE)
    return TITLE


async def add_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(ASK_DESCRIPTION)
    return DESCRIPTION


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = ""
    await update.message.reply_text(SKIPPED_DESC)
    await update.message.reply_text(ASK_DEADLINE)
    return DEADLINE


async def add_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text(ASK_DEADLINE)
    return DEADLINE


async def add_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deadline_raw = update.message.text.strip()
    deadline = parse_deadline(deadline_raw)
    if not deadline:
        await update.message.reply_text(INVALID_DATE)
        return DEADLINE
    context.user_data["deadline"] = deadline
    await update.message.reply_text(ASK_ASSIGNEE)
    return ASSIGNEE


async def add_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assignee_raw = update.message.text.strip()
    title = context.user_data["title"]
    deadline = context.user_data["deadline"]
    description = context.user_data.get("description", "")

    assignee_id = None
    user_data = get_user_by_username(assignee_raw)
    if user_data:
        assignee_id = user_data["user_id"]

    task_id = add_task(title, assignee_raw, deadline, description, assignee_id)
    desc_text = f"📋 {description}" if description else ""
    await update.message.reply_text(
        TASK_ADDED.format(id=task_id, title=title, deadline=format_datetime_ru(deadline), assignee=assignee_raw, description=desc_text),
        reply_markup=task_actions_keyboard(task_id),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(CANCELLED)
    context.user_data.clear()
    return ConversationHandler.END


# ── List ─────────────────────────────────────────────────

async def list_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID
    show_all = is_admin and context.args and context.args[0] == "all"

    if show_all:
        tasks = list_tasks(include_done=False)
    else:
        tasks = list_tasks(include_done=False, user_id=user_id)

    if not tasks:
        await update.message.reply_text(NO_TASKS)
        return

    lines = []
    for t in tasks:
        status_icon = "🟢" if t["status"] == "active" else "🔴"
        desc = f" - {t['description']}" if t["description"] else ""
        lines.append(
            f"{status_icon} #{t['id']} <b>{t['title']}</b>{desc}\n"
            f"   ⏰ {t['deadline']} | 👤 {t['assignee']}"
        )

    await update.message.reply_text(
        "\n\n".join(lines), parse_mode="HTML",
    )


# ── Done (with approval) ─────────────────────────────────

async def done_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text(INVALID_ID)
        return

    task = get_task(task_id)
    if not task:
        await update.message.reply_text(TASK_NOT_FOUND.format(id=task_id))
        return

    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID

    if is_admin:
        update_task_status(task_id, "done")
        await update.message.reply_text(TASK_DONE.format(id=task_id))
    else:
        update_task_status(task_id, "pending_approval")
        await update.message.reply_text(DONE_SENT_TO_ADMIN)

        text = DONE_REQUESTED.format(id=task_id, title=task["title"])
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=text,
                reply_markup=approval_keyboard(task_id),
            )
        except Exception:
            pass


# ── Delete ───────────────────────────────────────────────

async def delete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text(INVALID_ID)
        return

    if delete_task(task_id):
        await update.message.reply_text(TASK_DELETED.format(id=task_id))
    else:
        await update.message.reply_text(TASK_NOT_FOUND.format(id=task_id))


# ── Users management (admin) ─────────────────────────────

async def users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(ADMIN_ONLY)
        return
    users = list_users()
    if not users:
        await update.message.reply_text(NO_USERS)
        return
    lines = []
    for u in users:
        name = u["full_name"] or u["username"] or f"ID {u['user_id']}"
        created = u["created_at"][:10]
        lines.append(f"🆔 <code>{u['user_id']}</code> — {name} (@{u['username']}) — с {created}")
    await update.message.reply_text(
        "📋 <b>Зарегистрированные пользователи:</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )


async def removeuser_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(ADMIN_ONLY)
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Укажите ID пользователя: /removeuser <id>")
        return
    if target_id == ADMIN_ID:
        await update.message.reply_text(USER_REMOVE_DENIED)
        return
    if not get_user(target_id):
        await update.message.reply_text(USER_NOT_FOUND.format(user_id=target_id))
        return
    delete_user(target_id)
    await update.message.reply_text(USER_REMOVED.format(user_id=target_id))


# ── Overdue / Pending ────────────────────────────────────

async def overdue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = list_overdue(user_id=user_id if user_id != ADMIN_ID else None)
    if not tasks:
        await update.message.reply_text(NO_OVERDUE)
        return
    lines = []
    for t in tasks:
        lines.append(
            f"🔴 #{t['id']} <b>{t['title']}</b>\n   ⏰ {t['deadline']} | 👤 {t['assignee']}"
        )
    await update.message.reply_text(
        "⚠️ <b>Просроченные задачи:</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML",
    )


async def pending_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = list_pending_approval()
    if not tasks:
        await update.message.reply_text(NO_PENDING)
        return
    lines = []
    for t in tasks:
        lines.append(
            f"⏳ #{t['id']} <b>{t['title']}</b>\n   👤 {t['assignee']} | ⏰ {t['deadline']}"
        )
    await update.message.reply_text(
        "📬 <b>Задачи на подтверждении:</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML",
    )


# ── Callback (buttons) ───────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    # User marks as done
    if data.startswith("done_"):
        task_id = int(data.split("_")[1])
        task = get_task(task_id)
        if not task:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))
            return

        if user_id == ADMIN_ID:
            update_task_status(task_id, "done")
            await query.edit_message_text(TASK_DONE.format(id=task_id))
        else:
            update_task_status(task_id, "pending_approval")
            await query.edit_message_text(DONE_SENT_TO_ADMIN)

            text = DONE_REQUESTED.format(id=task_id, title=task["title"])
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=text,
                    reply_markup=approval_keyboard(task_id),
                )
            except Exception:
                pass

    # Admin approves
    elif data.startswith("approve_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Только администратор может подтверждать.")
            return
        task_id = int(data.split("_")[1])
        task = get_task(task_id)
        if not task:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))
            return
        update_task_status(task_id, "done")
        await query.edit_message_text(DONE_APPROVED.format(id=task_id))
        if task.get("assignee_id"):
            try:
                await context.bot.send_message(
                    chat_id=task["assignee_id"],
                    text=DONE_APPROVED.format(id=task_id),
                )
            except Exception:
                pass

    # Admin rejects
    elif data.startswith("reject_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Только администратор может отклонять.")
            return
        task_id = int(data.split("_")[1])
        task = get_task(task_id)
        if not task:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))
            return
        update_task_status(task_id, "active")
        await query.edit_message_text(DONE_REJECTED.format(id=task_id))
        if task.get("assignee_id"):
            try:
                await context.bot.send_message(
                    chat_id=task["assignee_id"],
                    text=DONE_REJECTED.format(id=task_id),
                )
            except Exception:
                pass

    # Delete
    elif data.startswith("delete_"):
        task_id = int(data.split("_")[1])
        if delete_task(task_id):
            await query.edit_message_text(TASK_DELETED.format(id=task_id))
        else:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))


# ── Handlers list ───────────────────────────────────────

def get_handlers():
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            MessageHandler(filters.Regex(r"(?i)\bзадача\b"), add_start),
        ],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_description),
                CommandHandler("skip", skip_description),
            ],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_deadline)],
            ASSIGNEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_assignee)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    return [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        conv_handler,
        CommandHandler("list", list_tasks_handler),
        CommandHandler("done", done_task_handler),
        CommandHandler("delete", delete_task_handler),
        CommandHandler("overdue", overdue_handler),
        CommandHandler("pending", pending_handler),
        CommandHandler("users", users_handler),
        CommandHandler("removeuser", removeuser_handler),
        CallbackQueryHandler(button_callback),
    ]
