import re
from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from db.crud import add_task, list_tasks, get_task, update_task_status, delete_task, list_overdue
from bot.messages import HELP_TEXT, TASK_ADDED, TASK_DONE, TASK_NOT_FOUND, TASK_DELETED, NO_TASKS, INVALID_FORMAT, INVALID_ID, NO_OVERDUE, INVALID_DATE
from bot.keyboards import task_actions_keyboard
from utils.date_parser import parse_deadline, format_datetime_ru


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для управления задачами.\n" + HELP_TEXT
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def add_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text[len("/add "):].strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*", text)]

    if len(parts) < 3:
        await update.message.reply_text(INVALID_FORMAT)
        return

    title, deadline_raw, assignee = parts[0], parts[1], parts[2]
    description = parts[3] if len(parts) > 3 else ""

    deadline = parse_deadline(deadline_raw)
    if not deadline:
        await update.message.reply_text(INVALID_DATE)
        return

    task_id = add_task(title, assignee, deadline, description)

    await update.message.reply_text(
        TASK_ADDED.format(id=task_id, title=title, deadline=format_datetime_ru(deadline), assignee=assignee),
        reply_markup=task_actions_keyboard(task_id),
    )


async def list_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = list_tasks()
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
        "\n\n".join(lines),
        parse_mode="HTML",
    )


async def done_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text(INVALID_ID)
        return

    if update_task_status(task_id, "done"):
        await update.message.reply_text(TASK_DONE.format(id=task_id))
    else:
        await update.message.reply_text(TASK_NOT_FOUND.format(id=task_id))


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


async def overdue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = list_overdue()
    if not tasks:
        await update.message.reply_text(NO_OVERDUE)
        return

    lines = []
    for t in tasks:
        lines.append(
            f"🔴 #{t['id']} <b>{t['title']}</b>\n"
            f"   ⏰ {t['deadline']} | 👤 {t['assignee']}"
        )

    await update.message.reply_text(
        "⚠️ <b>Просроченные задачи:</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML",
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("done_"):
        task_id = int(data.split("_")[1])
        if update_task_status(task_id, "done"):
            await query.edit_message_text(TASK_DONE.format(id=task_id))
        else:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))
    elif data.startswith("delete_"):
        task_id = int(data.split("_")[1])
        if delete_task(task_id):
            await query.edit_message_text(TASK_DELETED.format(id=task_id))
        else:
            await query.edit_message_text(TASK_NOT_FOUND.format(id=task_id))


def get_handlers():
    return [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        CommandHandler("add", add_task_handler),
        CommandHandler("list", list_tasks_handler),
        CommandHandler("done", done_task_handler),
        CommandHandler("delete", delete_task_handler),
        CommandHandler("overdue", overdue_handler),
        CallbackQueryHandler(button_callback),
    ]
