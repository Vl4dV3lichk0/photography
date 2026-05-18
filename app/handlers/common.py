from __future__ import annotations

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db import Database
from app.keyboards import admin_menu_kb, main_menu_kb
from app.texts import format_schedule_preview

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, db: Database) -> None:
    rows = await db.schedule_preview(days=21)
    await message.answer(format_schedule_preview(rows), reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start - расписание и запись\n"
        "/my - мои записи\n"
        "/admin - панель администратора"
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, db: Database) -> None:
    if not await db.is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к панели администратора.")
        return
    await message.answer("Панель администратора", reply_markup=admin_menu_kb())


def register_common_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)