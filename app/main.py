from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import load_settings
from app.db import Database
from app.handlers import register_handlers
from app.services.scheduler import notifications_loop


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()

    db = Database(settings.database_url)
    await db.connect()
    await db.init_schema()
    await db.seed_admins(settings.admin_ids, settings.owner_tg_id)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    register_handlers(dp)

    scheduler_task = asyncio.create_task(notifications_loop(bot, db, settings))
    try:
        await dp.start_polling(bot, db=db, settings=settings)
    finally:
        scheduler_task.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())