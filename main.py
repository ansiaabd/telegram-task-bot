from telegram.ext import Application
from config import BOT_TOKEN
from db.crud import init_db
from bot.handlers import get_handlers


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set. Export it or set in .env")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    for handler in get_handlers():
        app.add_handler(handler)

    print("🤖 Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
