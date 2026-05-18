from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

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
    await setup_bot_commands(bot, settings.admin_ids)
    dp = Dispatcher()
    register_handlers(dp)

    scheduler_task = asyncio.create_task(notifications_loop(bot, db, settings))
    try:
        await dp.start_polling(bot, db=db, settings=settings)
    finally:
        scheduler_task.cancel()
        await db.close()
        await bot.session.close()


async def setup_bot_commands(bot: Bot, admin_ids: list[int]) -> None:
    user_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="price", description="Прайс"),
        BotCommand(command="my", description="Мои активные записи"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = [
        BotCommand(command="start", description="Панель администратора"),
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="price", description="Прайс"),
        BotCommand(command="archive_now", description="Запустить архивацию"),
        BotCommand(command="help", description="Помощь"),
    ]
    for admin_id in admin_ids:
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))


if __name__ == "__main__":
    asyncio.run(main())