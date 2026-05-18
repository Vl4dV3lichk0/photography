from __future__ import annotations

from datetime import datetime

from aiogram import Dispatcher, F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from app.db import Database
from app.keyboards import admin_menu_kb, cities_kb, pending_action_kb
from app.states import AdminAddCityState, AdminBlockState, AdminWorkingWindowState
from app.texts import format_hours

router = Router()


def _parse_date(raw: str):
    return datetime.strptime(raw.strip(), "%Y-%m-%d").date()


def _parse_hours(raw: str) -> tuple[int, int]:
    left, right = raw.strip().split("-")
    start, end = int(left), int(right)
    if start < 0 or end > 24 or end <= start:
        raise ValueError("Некорректный диапазон")
    return start, end


async def _ensure_admin(callback: CallbackQuery, db: Database) -> bool:
    ok = await db.is_admin(callback.from_user.id)
    if not ok:
        await callback.answer("Недостаточно прав", show_alert=True)
    return ok


@router.callback_query(F.data == "admin:add_city")
async def admin_add_city_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    await state.set_state(AdminAddCityState.waiting_city_name)
    await callback.message.answer("Введите название города")
    await callback.answer()


@router.message(AdminAddCityState.waiting_city_name)
async def admin_add_city_save(message: Message, state: FSMContext, db: Database) -> None:
    await db.add_city(message.text.strip())
    await state.clear()
    await message.answer("Город сохранен", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin:set_window")
async def admin_set_window_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    cities = await db.list_cities()
    if not cities:
        await callback.message.answer("Сначала добавьте хотя бы один город.")
        await callback.answer()
        return
    await state.set_state(AdminWorkingWindowState.waiting_city)
    await callback.message.answer("Выберите город", reply_markup=cities_kb(cities, "adminwindow"))
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindow:city:"))
async def admin_set_window_city(callback: CallbackQuery, state: FSMContext) -> None:
    city_id = int(callback.data.split(":")[-1])
    await state.update_data(city_id=city_id)
    await state.set_state(AdminWorkingWindowState.waiting_date)
    await callback.message.answer("Введите дату в формате YYYY-MM-DD")
    await callback.answer()


@router.message(AdminWorkingWindowState.waiting_date)
async def admin_set_window_date(message: Message, state: FSMContext) -> None:
    try:
        day = _parse_date(message.text)
    except Exception:
        await message.answer("Неверная дата, используйте YYYY-MM-DD")
        return
    await state.update_data(work_date=day.isoformat())
    await state.set_state(AdminWorkingWindowState.waiting_hours)
    await message.answer("Введите рабочие часы в формате 10-18")


@router.message(AdminWorkingWindowState.waiting_hours)
async def admin_set_window_hours(message: Message, state: FSMContext, db: Database) -> None:
    try:
        start, end = _parse_hours(message.text)
    except Exception:
        await message.answer("Неверный диапазон. Пример: 10-18")
        return

    data = await state.get_data()
    ok, info = await db.set_working_window(
        city_id=int(data["city_id"]),
        work_date=_parse_date(data["work_date"]),
        start_hour=start,
        end_hour=end,
        created_by=message.from_user.id,
    )
    await state.clear()
    await message.answer(info if ok else f"Ошибка: {info}", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin:add_block")
async def admin_add_block_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    cities = await db.list_cities()
    if not cities:
        await callback.message.answer("Нет городов. Сначала добавьте город.")
        await callback.answer()
        return
    await state.set_state(AdminBlockState.waiting_city)
    await callback.message.answer("Город для блокировки", reply_markup=cities_kb(cities, "adminblock"))
    await callback.answer()


@router.callback_query(F.data.startswith("adminblock:city:"))
async def admin_add_block_city(callback: CallbackQuery, state: FSMContext) -> None:
    city_id = int(callback.data.split(":")[-1])
    await state.update_data(city_id=city_id)
    await state.set_state(AdminBlockState.waiting_date)
    await callback.message.answer("Введите дату блокировки YYYY-MM-DD")
    await callback.answer()


@router.message(AdminBlockState.waiting_date)
async def admin_add_block_date(message: Message, state: FSMContext) -> None:
    try:
        day = _parse_date(message.text)
    except Exception:
        await message.answer("Неверная дата")
        return
    await state.update_data(block_date=day.isoformat())
    await state.set_state(AdminBlockState.waiting_hours)
    await message.answer("Введите диапазон часов блокировки, пример 13-15")


@router.message(AdminBlockState.waiting_hours)
async def admin_add_block_hours(message: Message, state: FSMContext) -> None:
    try:
        start, end = _parse_hours(message.text)
    except Exception:
        await message.answer("Неверный диапазон")
        return
    await state.update_data(start_hour=start, end_hour=end)
    await state.set_state(AdminBlockState.waiting_reason)
    await message.answer("Введите причину блокировки")


@router.message(AdminBlockState.waiting_reason)
async def admin_add_block_reason(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await db.add_time_block(
        city_id=int(data["city_id"]),
        block_date=_parse_date(data["block_date"]),
        start_hour=int(data["start_hour"]),
        end_hour=int(data["end_hour"]),
        reason=message.text.strip(),
        created_by=message.from_user.id,
    )
    await state.clear()
    await message.answer("Блокировка сохранена", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin:pending")
async def admin_pending_list(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    rows = await db.pending_bookings()
    if not rows:
        await callback.message.answer("Нет заявок на подтверждение.")
        await callback.answer()
        return

    for row in rows:
        txt = (
            f"Заявка #{row['id']}\n"
            f"Город: {row['city_name']}\n"
            f"Дата: {row['booking_date'].strftime('%d.%m.%Y')}\n"
            f"Часы: {format_hours(row['hours'])}\n"
            f"Контакт: {row['tg_contact']}\n"
            f"Имя: {row['client_name'] or '-'}\n"
            f"Телефон: {row['phone'] or '-'}\n"
            f"Тип съемки: {row['shoot_type'] or '-'}\n"
            f"Комментарий: {row['comment'] or '-'}"
        )
        await callback.message.answer(txt, reply_markup=pending_action_kb(row["id"]))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:approve:"))
async def admin_approve(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    booking_id = int(callback.data.split(":")[-1])
    ok = await db.update_booking_status(booking_id, "confirmed", callback.from_user.id)
    if not ok:
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    booking = await db.get_booking(booking_id)
    if booking:
        await callback.bot.send_message(
            booking["user_tg_id"],
            (
                f"Ваша запись #{booking_id} подтверждена\n"
                f"{booking['city_name']} {booking['booking_date'].strftime('%d.%m.%Y')}\n"
                f"Часы: {format_hours(booking['hours'])}"
            ),
        )
    await callback.message.answer(f"Заявка #{booking_id} подтверждена")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:reject:"))
async def admin_reject(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    booking_id = int(callback.data.split(":")[-1])
    ok = await db.update_booking_status(booking_id, "rejected", callback.from_user.id)
    if not ok:
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    booking = await db.get_booking(booking_id)
    if booking:
        await callback.bot.send_message(
            booking["user_tg_id"],
            f"К сожалению, заявка #{booking_id} отклонена. Выберите другое время через /start.",
        )
    await callback.message.answer(f"Заявка #{booking_id} отклонена")
    await callback.answer()


def register_admin_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)