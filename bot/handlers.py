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

from db.crud import add_task, list_tasks, get_task, update_task_status, delete_task, list_overdue
from bot.messages import (
    HELP_TEXT,
    TASK_ADDED,
    TASK_DONE,
    TASK_NOT_FOUND,
    TASK_DELETED,
    NO_TASKS,
    INVALID_ID,
    NO_OVERDUE,
    INVALID_DATE,
    ASK_TITLE,
    ASK_DESCRIPTION,
    ASK_DEADLINE,
    ASK_ASSIGNEE,
    CANCELLED,
    SKIPPED_DESC,
)
from bot.keyboards import task_actions_keyboard
from utils.date_parser import parse_deadline, format_datetime_ru

TITLE, DESCRIPTION, DEADLINE, ASSIGNEE = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для управления задачами.\n" + HELP_TEXT
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # inline format: "задача / title / deadline / assignee" or "/add title / deadline / assignee"
    parts = [p.strip() for p in re.split(r"\s*/\s*", text)]
    # remove trigger word ("задача" or "/add")
    if parts[0].lower().lstrip("/") in ("задача", "add"):
        parts = parts[1:]

    if len(parts) >= 3:
        title = parts[0]
        candidate_deadline = parse_deadline(parts[1])
        if candidate_deadline:
            deadline = candidate_deadline
            assignee = parts[2]
            description = " / ".join(parts[3:]) if len(parts) > 3 else ""
        else:
            title = parts[0]
            description = parts[1]
            if len(parts) >= 3:
                deadline = parse_deadline(parts[2])
                if not deadline:
                    await update.message.reply_text(INVALID_DATE)
                    return ConversationHandler.END
                assignee = " / ".join(parts[3:]) if len(parts) > 3 else ""

        task_id = add_task(title, assignee, deadline, description)
        desc_text = f"📋 {description}" if description else ""
        await update.message.reply_text(
            TASK_ADDED.format(id=task_id, title=title, deadline=format_datetime_ru(deadline), assignee=assignee, description=desc_text),
            reply_markup=task_actions_keyboard(task_id),
        )
        return ConversationHandler.END

    # start conversation flow
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
    assignee = update.message.text.strip()
    title = context.user_data["title"]
    deadline = context.user_data["deadline"]
    description = context.user_data.get("description", "")

    task_id = add_task(title, assignee, deadline, description)

    desc_text = f"📋 {description}" if description else ""
    await update.message.reply_text(
        TASK_ADDED.format(id=task_id, title=title, deadline=format_datetime_ru(deadline), assignee=assignee, description=desc_text),
        reply_markup=task_actions_keyboard(task_id),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(CANCELLED)
    context.user_data.clear()
    return ConversationHandler.END


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
        CallbackQueryHandler(button_callback),
    ]
