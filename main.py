from telegram.ext import Application

from config import BOT_TOKEN
from db.crud import init_db
from bot.handlers import get_handlers
from scheduler.tasks import check_overdue


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    for handler in get_handlers():
        app.add_handler(handler)

    app.job_queue.run_repeating(check_overdue, interval=60, first=10)

    print("🤖 Bot started. Press Ctrl+C to stop.", flush=True)
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
