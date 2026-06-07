import asyncio
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import BOT_TOKEN
from db.crud import init_db
from bot.handlers import get_handlers
from scheduler.tasks import check_overdue


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set. Export it or set in .env")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    for handler in get_handlers():
        app.add_handler(handler)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_overdue,
        trigger="interval",
        minutes=1,
        args=[app],
        id="check_overdue",
        replace_existing=True,
    )

    async with app:
        scheduler.start()
        print("🤖 Bot started. Press Ctrl+C to stop.")
        await app.start()
        await app.updater.start_polling(allowed_updates=["message", "callback_query"])
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
