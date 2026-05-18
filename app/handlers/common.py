from __future__ import annotations

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db import Database
from app.keyboards import admin_menu_kb, main_menu_kb
from app.texts import format_price_offer, format_start_message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, db: Database) -> None:
    rows = await db.schedule_preview(days=90, limit=15)
    pricing = await db.get_pricing()
    await message.answer(
        format_start_message(rows, pricing["hourly_price"], pricing["currency"]),
        reply_markup=main_menu_kb(),
    )


@router.message(Command("price"))
async def cmd_price(message: Message, db: Database) -> None:
    pricing = await db.get_pricing()
    await message.answer(
        format_price_offer(pricing["hourly_price"], pricing["currency"]),
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "info:price")
async def cb_price(callback: CallbackQuery, db: Database) -> None:
    pricing = await db.get_pricing()
    await callback.message.answer(
        format_price_offer(pricing["hourly_price"], pricing["currency"]),
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start - расписание и запись\n"
        "/price - прайс\n"
        "/my - мои записи\n"
        "/admin - панель администратора\n"
        "/archive_now - ручная архивация (для админов)"
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, db: Database) -> None:
    if not await db.is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к панели администратора.")
        return
    await message.answer("Панель администратора", reply_markup=admin_menu_kb())


def register_common_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)