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
    get_user, get_user_role, set_user_role, list_users, delete_user,
)
from bot.messages import (
    HELP_TEXT, TASK_ADDED, TASK_DONE, TASK_NOT_FOUND, TASK_DELETED,
    NO_TASKS, INVALID_ID, NO_OVERDUE, INVALID_DATE,
    ASK_TITLE, ASK_DESCRIPTION, ASK_DEADLINE, ASK_ASSIGNEE,
    CANCELLED, SKIPPED_DESC, REGISTERED,
    DONE_REQUESTED, DONE_APPROVED, DONE_REJECTED, DONE_SENT_TO_ADMIN,
    NO_PENDING, NO_USERS, USER_REMOVED, USER_REMOVE_DENIED, USER_NOT_FOUND, ADMIN_ONLY,
    USER_PROMOTED, USER_DEMOTED, USER_ALREADY_ADMIN, MODERATOR_ONLY,
    NEW_TASK_NOTIFICATION, DONE_WHICH_TASK, DONE_NO_ACTIVE,
)
from bot.keyboards import task_actions_keyboard, approval_keyboard, user_picker_keyboard, menu_keyboard
from utils.date_parser import parse_deadline, format_datetime_ru
from config import ADMIN_ID


def _get_role(user_id: int) -> str:
    if user_id == ADMIN_ID:
        return "admin"
    return get_user_role(user_id)


def _can_approve(user_id: int, task: dict) -> bool:
    return user_id == ADMIN_ID or task.get("created_by") == user_id


async def notify_assignee(context: ContextTypes.DEFAULT_TYPE, task_id: int, title: str, deadline: str, assignee: str, assignee_id: int):
    if not assignee_id:
        return
    text = NEW_TASK_NOTIFICATION.format(id=task_id, title=title, deadline=deadline, assignee=assignee)
    try:
        await context.bot.send_message(chat_id=assignee_id, text=text, parse_mode="HTML")
    except Exception:
        pass


ASSIGNEE, TITLE, DESCRIPTION, DEADLINE = range(4)


# ── Start / Registration ─────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Привет, администратор!\n" + HELP_TEXT
        )
    else:
        register_user(user.id, user.username or "", user.full_name or user.first_name)
        role = get_user_role(user.id)
        prefix = "🛡 " if role == "moderator" else ""
        await update.message.reply_text(
            prefix + REGISTERED.format(name=user.full_name or user.first_name)
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 <b>Быстрое меню</b>",
        parse_mode="HTML",
        reply_markup=menu_keyboard(),
    )


# ── Add task (inline + conversation) ─────────────────────

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*", text)]

    first = parts[0].lower().lstrip("/")
    if first in ("задача", "add"):
        parts = parts[1:]
    elif first.startswith("задача ") or first.startswith("add "):
        trigger = "задача" if first.startswith("задача") else "add"
        rest = parts[0][len(trigger):].strip()
        parts = [rest] + parts[1:]

    creator_id = update.effective_user.id

    if len(parts) >= 3:
        title = parts[0]
        deadline = None
        desc_parts = []
        assignee_parts = []
        found_deadline = False
        for p in parts[1:]:
            if not found_deadline:
                d = parse_deadline(p)
                if d:
                    deadline = d
                    found_deadline = True
                else:
                    desc_parts.append(p)
            else:
                assignee_parts.append(p)
        if not deadline:
            await update.message.reply_text(INVALID_DATE)
            return ConversationHandler.END
        description = " / ".join(desc_parts)
        assignee_raw = " / ".join(assignee_parts)

        assignee_id = None
        user_data = get_user_by_username(assignee_raw)
        if user_data:
            assignee_id = user_data["user_id"]

        task_id = add_task(title, assignee_raw, deadline, description, assignee_id, creator_id)
        desc_text = f"📋 {description}" if description else ""
        await update.message.reply_text(
            TASK_ADDED.format(id=task_id, title=title, deadline=format_datetime_ru(deadline), assignee=assignee_raw, description=desc_text),
            reply_markup=task_actions_keyboard(task_id),
        )
        await notify_assignee(context, task_id, title, format_datetime_ru(deadline), assignee_raw, assignee_id)
        return ConversationHandler.END

    context.user_data.clear()
    return await _ask_assignee(update, context)


async def _ask_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = list_users()
    if users:
        await update.message.reply_text(
            "👤 Выберите исполнителя:",
            reply_markup=user_picker_keyboard(users, update.effective_user.id),
        )
    else:
        await update.message.reply_text(ASK_ASSIGNEE)
    return ASSIGNEE


async def assignee_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_done_id"):
        return await _handle_awaiting_done(update, context)
    assignee_raw = update.message.text.strip()
    user_data = get_user_by_username(assignee_raw)
    context.user_data["assignee_id"] = user_data["user_id"] if user_data else None
    context.user_data["assignee_raw"] = assignee_raw
    await update.message.reply_text(ASK_TITLE)
    return TITLE


async def assignee_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "assignee_self":
        user = update.effective_user
        context.user_data["assignee_id"] = user.id
        context.user_data["assignee_raw"] = user.full_name or user.first_name or f"ID {user.id}"
    elif data.startswith("assignee_"):
        uid = int(data.split("_")[1])
        u = get_user(uid)
        if u:
            context.user_data["assignee_id"] = uid
            context.user_data["assignee_raw"] = u.get("full_name") or u.get("username") or f"ID {uid}"

    await query.edit_message_text(f"✅ Исполнитель: {context.user_data['assignee_raw']}")
    await query.message.reply_text(ASK_TITLE)
    return TITLE


async def add_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_done_id"):
        return await _handle_awaiting_done(update, context)
    text = update.message.text.strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*", text)]

    if len(parts) >= 2:
        title = parts[0]
        deadline = None
        desc_parts = []
        for p in parts[1:]:
            d = parse_deadline(p)
            if d and not deadline:
                deadline = d
            elif not deadline:
                desc_parts.append(p)
        if deadline:
            context.user_data["title"] = title
            context.user_data["description"] = " / ".join(desc_parts)
            context.user_data["deadline"] = deadline
            return await _finish_task(update, context)

    context.user_data["title"] = text
    await update.message.reply_text(ASK_DESCRIPTION)
    return DESCRIPTION


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = ""
    await update.message.reply_text(SKIPPED_DESC)
    await update.message.reply_text(ASK_DEADLINE)
    return DEADLINE


async def add_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_done_id"):
        return await _handle_awaiting_done(update, context)
    text = update.message.text.strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*", text)]

    if len(parts) >= 2:
        desc_text = parts[0]
        deadline = parse_deadline(parts[1])
        if deadline:
            context.user_data["description"] = desc_text
            context.user_data["deadline"] = deadline
            return await _finish_task(update, context)

    context.user_data["description"] = text
    await update.message.reply_text(ASK_DEADLINE)
    return DEADLINE


async def _handle_awaiting_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(INVALID_ID)
        return
    task = get_task(task_id)
    if not task:
        await update.message.reply_text(TASK_NOT_FOUND.format(id=task_id))
        return
    context.user_data.pop("awaiting_done_id", None)
    user_id = update.effective_user.id
    role = _get_role(user_id)
    if role == "admin" or _can_approve(user_id, task):
        update_task_status(task_id, "done")
        await update.message.reply_text(TASK_DONE.format(id=task_id))
    else:
        update_task_status(task_id, "pending_approval")
        await update.message.reply_text(DONE_SENT_TO_ADMIN)
        await _notify_approvers(context, task)


async def _finish_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data["title"]
    deadline = context.user_data["deadline"]
    description = context.user_data.get("description", "")
    assignee_raw = context.user_data["assignee_raw"]
    assignee_id = context.user_data.get("assignee_id")
    creator_id = update.effective_user.id

    task_id = add_task(title, assignee_raw, deadline, description, assignee_id, creator_id)
    desc_text = f"📋 {description}" if description else ""
    await update.message.reply_text(
        TASK_ADDED.format(id=task_id, title=title, deadline=format_datetime_ru(deadline), assignee=assignee_raw, description=desc_text),
        reply_markup=task_actions_keyboard(task_id),
    )
    await notify_assignee(context, task_id, title, format_datetime_ru(deadline), assignee_raw, assignee_id)
    context.user_data.clear()
    return ConversationHandler.END


async def add_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deadline_raw = update.message.text.strip()
    deadline = parse_deadline(deadline_raw)
    if not deadline:
        await update.message.reply_text(INVALID_DATE)
        return DEADLINE
    context.user_data["deadline"] = deadline
    return await _finish_task(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(CANCELLED)
    context.user_data.clear()
    return ConversationHandler.END


# ── List ─────────────────────────────────────────────────

async def list_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = _get_role(user_id)
    show_all = role == "admin" and context.args and context.args[0] == "all"

    if show_all:
        tasks = list_tasks(include_done=False)
    elif role == "admin":
        tasks = list_tasks(include_done=False)
    else:
        tasks = list_tasks(include_done=False, user_id=user_id, role=role)

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
    except IndexError:
        context.user_data["awaiting_done_id"] = True
        await update.message.reply_text(
            "📋 Напишите ID задачи, которую выполнили:"
        )
        return
    except ValueError:
        await update.message.reply_text(INVALID_ID)
        return

    task = get_task(task_id)
    if not task:
        await update.message.reply_text(TASK_NOT_FOUND.format(id=task_id))
        return

    user_id = update.effective_user.id
    role = _get_role(user_id)

    if role == "admin" or _can_approve(user_id, task):
        update_task_status(task_id, "done")
        await update.message.reply_text(TASK_DONE.format(id=task_id))
    else:
        update_task_status(task_id, "pending_approval")
        await update.message.reply_text(DONE_SENT_TO_ADMIN)
        await _notify_approvers(context, task)


async def _notify_approvers(context: ContextTypes.DEFAULT_TYPE, task: dict):
    task_id = task["id"]
    text = DONE_REQUESTED.format(id=task_id, title=task["title"])

    notified = set()
    if task.get("created_by"):
        try:
            await context.bot.send_message(
                chat_id=task["created_by"],
                text=text,
                reply_markup=approval_keyboard(task_id),
            )
            notified.add(task["created_by"])
        except Exception:
            pass

    if ADMIN_ID not in notified:
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
        role_badge = "⭐ " if u["role"] == "admin" else "🛡 " if u["role"] == "moderator" else ""
        lines.append(f"{role_badge}🆔 <code>{u['user_id']}</code> — {name} (@{u['username']}) — {u['role']} — с {created}")
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


# ── Promote / Demote (admin) ─────────────────────────────

async def promote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(ADMIN_ONLY)
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Укажите ID пользователя: /promote <id>")
        return
    if target_id == ADMIN_ID:
        await update.message.reply_text(USER_ALREADY_ADMIN)
        return
    if not get_user(target_id):
        await update.message.reply_text(USER_NOT_FOUND.format(user_id=target_id))
        return
    set_user_role(target_id, "moderator")
    await update.message.reply_text(USER_PROMOTED.format(user_id=target_id))
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="🛡 Вам назначена роль модератора! Теперь вы можете создавать задачи и подтверждать выполнение.",
        )
    except Exception:
        pass


async def demote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(ADMIN_ONLY)
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Укажите ID пользователя: /demote <id>")
        return
    if target_id == ADMIN_ID:
        await update.message.reply_text(USER_ALREADY_ADMIN)
        return
    if not get_user(target_id):
        await update.message.reply_text(USER_NOT_FOUND.format(user_id=target_id))
        return
    set_user_role(target_id, "user")
    await update.message.reply_text(USER_DEMOTED.format(user_id=target_id))
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="🔄 Ваша роль модератора отозвана.",
        )
    except Exception:
        pass


# ── Overdue / Pending ────────────────────────────────────

async def overdue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = _get_role(user_id)
    tasks = list_overdue(user_id=None if role == "admin" else user_id, role=role)
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
    user_id = update.effective_user.id
    role = _get_role(user_id)
    if role not in ("admin", "moderator"):
        await update.message.reply_text(MODERATOR_ONLY)
        return
    tasks = list_pending_approval(user_id=user_id, role=role)
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


# ── Natural language done (выполнено / сделано) ──────────

async def done_natural(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = _get_role(user_id)
    tasks = list_tasks(include_done=False, user_id=user_id, role=role)

    if not tasks:
        await update.message.reply_text(DONE_NO_ACTIVE)
        return

    if len(tasks) == 1:
        task = tasks[0]
        await _request_done_approval(update, context, task)
    else:
        lines = [f"#{t['id']} — {t['title']} (⏰ {t['deadline']})" for t in tasks]
        await update.message.reply_text(
            DONE_WHICH_TASK + "\n" + "\n".join(lines)
        )
        context.user_data["awaiting_done_id"] = True

    return


async def done_natural_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_done_id"):
        return
    try:
        task_id = int(update.message.text.strip())
    except ValueError:
        return
    task = get_task(task_id)
    if not task:
        await update.message.reply_text(TASK_NOT_FOUND.format(id=task_id))
        return
    context.user_data.pop("awaiting_done_id", None)
    await _request_done_approval(update, context, task)


async def _request_done_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, task: dict):
    task_id = task["id"]
    user_id = update.effective_user.id
    role = _get_role(user_id)

    if role == "admin" or _can_approve(user_id, task):
        update_task_status(task_id, "done")
        await update.message.reply_text(TASK_DONE.format(id=task_id))
    else:
        update_task_status(task_id, "pending_approval")
        await update.message.reply_text(DONE_SENT_TO_ADMIN)
        await _notify_approvers(context, task)


# ── Callback (buttons) ───────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    if data.startswith("done_"):
        task_id = int(data.split("_")[1])
        task = get_task(task_id)
        if not task:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))
            return

        if _can_approve(user_id, task):
            update_task_status(task_id, "done")
            await query.edit_message_text(TASK_DONE.format(id=task_id))
        else:
            update_task_status(task_id, "pending_approval")
            await query.edit_message_text(DONE_SENT_TO_ADMIN)
            await _notify_approvers(context, task)

    elif data.startswith("approve_"):
        task_id = int(data.split("_")[1])
        task = get_task(task_id)
        if not task:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))
            return
        if not _can_approve(user_id, task):
            await query.edit_message_text("❌ Только создатель задачи или администратор может подтверждать.")
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

    elif data.startswith("reject_"):
        task_id = int(data.split("_")[1])
        task = get_task(task_id)
        if not task:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))
            return
        if not _can_approve(user_id, task):
            await query.edit_message_text("❌ Только создатель задачи или администратор может отклонять.")
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

    elif data.startswith("delete_"):
        task_id = int(data.split("_")[1])
        if delete_task(task_id):
            await query.edit_message_text(TASK_DELETED.format(id=task_id))
        else:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))

    # Menu buttons
    elif data == "menu_list":
        await query.answer()
        await list_tasks_handler(update, context)
    elif data == "menu_done":
        await query.answer()
        context.user_data["awaiting_done_id"] = True
        await query.message.reply_text("📋 Напишите ID задачи (например: 3):")
    elif data == "menu_overdue":
        await query.answer()
        await overdue_handler(update, context)
    elif data == "menu_help":
        await query.answer()
        await query.message.reply_text(HELP_TEXT)


# ── Handlers list ───────────────────────────────────────

def get_handlers():
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            MessageHandler(filters.Regex(r"(?i)\bзадача\b"), add_start),
        ],
        states={
            ASSIGNEE: [
                CallbackQueryHandler(assignee_callback, pattern=r"^assignee_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, assignee_text),
            ],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_description),
                CommandHandler("skip", skip_description),
            ],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_deadline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    return [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        CommandHandler("menu", menu_command),
        conv_handler,
        CommandHandler("list", list_tasks_handler),
        CommandHandler("done", done_task_handler),
        CommandHandler("delete", delete_task_handler),
        CommandHandler("overdue", overdue_handler),
        CommandHandler("pending", pending_handler),
        CommandHandler("users", users_handler),
        CommandHandler("removeuser", removeuser_handler),
        CommandHandler("promote", promote_handler),
        CommandHandler("demote", demote_handler),
        MessageHandler(filters.Regex(r"(?i)^(выполнено|сделано|готово)$") & ~filters.COMMAND, done_natural),
        MessageHandler(filters.Regex(r"^\d+$") & ~filters.COMMAND, done_natural_number),
        CallbackQueryHandler(button_callback),
    ]
