from __future__ import annotations

import json
from datetime import datetime

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.db import Database
from app.keyboards import (
    admin_archive_menu_kb,
    admin_active_action_kb,
    admin_bookings_menu_kb,
    admin_cities_menu_kb,
    admin_days_in_month_kb,
    admin_menu_kb,
    admin_months_kb,
    admin_schedule_menu_kb,
    admin_end_hour_kb,
    admin_start_hour_kb,
    archive_delete_confirm_kb,
    archived_item_kb,
    cities_kb,
    date_choice_kb,
    pending_action_kb,
    simple_back_kb,
    window_delete_confirm_kb,
)
from app.states import (
    AdminAddCityState,
    AdminArchiveState,
    AdminBlockState,
    AdminPriceState,
    AdminWindowDeleteState,
    AdminWorkingWindowState,
)
from app.texts import format_hour_ranges, format_price_offer, format_slots

router = Router()


def _parse_date(raw: str):
    return datetime.strptime(raw.strip(), "%Y-%m-%d").date()


def _parse_hours(raw: str) -> tuple[int, int]:
    left, right = raw.strip().split("-")
    start, end = int(left), int(right)
    if start < 0 or end > 24 or end <= start:
        raise ValueError("Некорректный диапазон")
    return start, end


def _parse_price(raw: str) -> int:
    value = int(raw.strip())
    if value < 0:
        raise ValueError("Цена не может быть отрицательной")
    return value


async def _ensure_admin(callback: CallbackQuery, db: Database) -> bool:
    ok = await db.is_admin(callback.from_user.id)
    if not ok:
        await callback.answer("Недостаточно прав", show_alert=True)
    return ok


async def _ensure_admin_message(message: Message, db: Database) -> bool:
    if not await db.is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-разделу.")
        return False
    return True


def _client_link(username: str | None, user_tg_id: int) -> str:
    if username:
        return f"@{username}"
    return f"<a href=\"tg://user?id={user_tg_id}\">Клиент</a>"


@router.callback_query(F.data == "admin:add_city")
async def admin_add_city_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    await state.set_state(AdminAddCityState.waiting_city_name)
    await callback.message.edit_text("Введите название города", reply_markup=simple_back_kb("admin:menu:cities"))
    await callback.answer()


@router.message(AdminAddCityState.waiting_city_name)
async def admin_add_city_save(message: Message, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin_message(message, db):
        return
    await db.add_city(message.text.strip())
    await state.clear()
    await message.answer("Город сохранен", reply_markup=admin_cities_menu_kb())


@router.callback_query(F.data == "admin:menu:root")
async def admin_menu_root(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    await callback.message.edit_text("Главное меню администратора", reply_markup=admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:menu:cities")
async def admin_menu_cities(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    await callback.message.edit_text("Раздел: Города", reply_markup=admin_cities_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:cities:list")
async def admin_cities_list(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    cities = await db.list_cities()
    if not cities:
        await callback.message.edit_text("Список городов пуст.", reply_markup=admin_cities_menu_kb())
        await callback.answer()
        return

    lines = ["Активные города:"]
    for city in cities:
        lines.append(f"- {city['name']}")
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_cities_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:menu:schedule")
async def admin_menu_schedule(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    await callback.message.edit_text("Раздел: Расписание", reply_markup=admin_schedule_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:schedule:available")
async def admin_schedule_available(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    rows = await db.schedule_preview(days=120, limit=50)
    if not rows:
        await callback.message.edit_text("Свободных окон для записи пока нет.", reply_markup=admin_schedule_menu_kb())
        await callback.answer()
        return

    chunks = ["Доступное расписание для записи:"]
    for row in rows:
        chunks.append(
            f"- {row['city_name']}: {row['work_date'].strftime('%d.%m.%Y')} {format_hour_ranges(row['free_hours'])}"
        )
    await callback.message.edit_text("\n".join(chunks), reply_markup=admin_schedule_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:menu:bookings")
async def admin_menu_bookings(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    await callback.message.edit_text("Раздел: Записи", reply_markup=admin_bookings_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:menu:archive")
async def admin_menu_archive(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    await callback.message.edit_text("Раздел: Архив", reply_markup=admin_archive_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:city:delete:start")
async def admin_delete_city_start(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    cities = await db.list_cities()
    if not cities:
        await callback.message.edit_text("Активных городов нет.", reply_markup=admin_cities_menu_kb())
        await callback.answer()
        return
    await callback.message.edit_text(
        "Выберите город для удаления",
        reply_markup=cities_kb(cities, "admincitydelete", "admin:menu:cities"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admincitydelete:city:"))
async def admin_delete_city_confirm(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    city_id = int(callback.data.split(":")[-1])
    result = await db.delete_city_cascade(city_id)
    if result["removed"] and result["affected"]:
        for row in result["affected"]:
            await callback.bot.send_message(
                row["user_tg_id"],
                (
                    f"Ваша запись #{row['id']} отменена администратором.\n"
                    "Причина: город удален из расписания.\n"
                    f"{row['city_name']} {row['booking_date'].strftime('%d.%m.%Y')}\n"
                    f"Часы: {format_slots(row['hours'])}"
                ),
            )
    await callback.message.edit_text(
        (
            f"Город удален. Отменено заявок: {len(result['affected'])}"
            if result["removed"]
            else "Город не найден."
        ),
        reply_markup=admin_cities_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:set_window")
async def admin_set_window_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    cities = await db.list_cities()
    if not cities:
        await callback.message.edit_text("Сначала добавьте хотя бы один город.")
        await callback.answer()
        return
    await state.set_state(AdminWorkingWindowState.waiting_city)
    await callback.message.edit_text(
        "Выберите город",
        reply_markup=cities_kb(cities, "adminwindow", "admin:menu:schedule"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindow:city:"))
async def admin_set_window_city(callback: CallbackQuery, state: FSMContext) -> None:
    city_id = int(callback.data.split(":")[-1])
    await state.update_data(city_id=city_id, month_offset=0)
    await state.set_state(AdminWorkingWindowState.waiting_date)
    await callback.message.edit_text(
        "Выберите месяц",
        reply_markup=admin_months_kb("adminwindow", 0, "admin:set_window"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindow:monthpage:"))
async def admin_set_window_month_page(callback: CallbackQuery, state: FSMContext) -> None:
    offset = int(callback.data.split(":")[-1])
    await state.update_data(month_offset=offset)
    await callback.message.edit_reply_markup(
        reply_markup=admin_months_kb("adminwindow", offset, "admin:set_window")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindow:month:"))
async def admin_set_window_month(callback: CallbackQuery, state: FSMContext) -> None:
    ym = callback.data.split(":")[-1]
    year, month = [int(x) for x in ym.split("-")]
    await state.update_data(selected_month=ym)
    await callback.message.edit_text(
        f"Выберите день {month:02d}.{year}",
        reply_markup=admin_days_in_month_kb("adminwindow", year, month, "admin:set_window"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindow:day:"))
async def admin_set_window_day(callback: CallbackQuery, state: FSMContext) -> None:
    work_date = callback.data.split(":")[-1]
    await state.update_data(work_date=work_date)
    await state.set_state(AdminWorkingWindowState.waiting_hours)
    await callback.message.edit_text(
        "Выберите начало рабочего дня",
        reply_markup=admin_start_hour_kb("adminwindow", "admin:set_window"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindow:start:"))
async def admin_set_window_start_hour(callback: CallbackQuery, state: FSMContext) -> None:
    start_hour = int(callback.data.split(":")[-1])
    await state.update_data(start_hour=start_hour)
    await callback.message.edit_text(
        "Выберите окончание рабочего дня",
        reply_markup=admin_end_hour_kb("adminwindow", start_hour, "admin:set_window"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindow:end:"))
async def admin_set_window_end_hour(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    end_hour = int(callback.data.split(":")[-1])
    data = await state.get_data()
    ok, info = await db.set_working_window(
        city_id=int(data["city_id"]),
        work_date=_parse_date(data["work_date"]),
        start_hour=int(data["start_hour"]),
        end_hour=end_hour,
        created_by=callback.from_user.id,
    )
    await state.clear()
    await callback.message.edit_text(info if ok else f"Ошибка: {info}", reply_markup=admin_schedule_menu_kb())
    await callback.answer()


@router.message(AdminWorkingWindowState.waiting_date)
async def admin_set_window_date(message: Message, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin_message(message, db):
        return
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
    if not await _ensure_admin_message(message, db):
        return
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
    await message.answer(info if ok else f"Ошибка: {info}", reply_markup=admin_schedule_menu_kb())


@router.callback_query(F.data == "admin:window:delete:start")
async def admin_window_delete_start(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    cities = await db.list_cities()
    if not cities:
        await callback.message.edit_text("Нет активных городов.", reply_markup=admin_schedule_menu_kb())
        await callback.answer()
        return
    await callback.message.edit_text(
        "Выберите город для удаления даты",
        reply_markup=cities_kb(cities, "adminwindelcity", "admin:menu:schedule"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindelcity:city:"))
async def admin_window_delete_city(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    city_id = int(callback.data.split(":")[-1])
    city = await db.get_city(city_id)
    dates = [row["work_date"] for row in await db.city_work_dates(city_id)]
    if not dates:
        await callback.message.edit_text("Для города нет дат расписания.", reply_markup=admin_schedule_menu_kb())
        await callback.answer()
        return
    await callback.message.edit_text(
        f"Выберите дату для удаления ({city['name']})",
        reply_markup=date_choice_kb(dates, f"adminwindeldate:{city_id}", "admin:menu:schedule"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminwindeldate:"))
async def admin_window_delete_date(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    payload = callback.data.split(":", 1)[1]
    city_id_raw, iso_day = payload.split(":")
    city_id = int(city_id_raw)
    day = datetime.strptime(iso_day, "%Y-%m-%d").date()

    result = await db.delete_working_window_cascade(city_id, day, force=False)
    if result["requires_confirmation"]:
        await state.set_state(AdminWindowDeleteState.waiting_active_confirm)
        await state.update_data(city_id=city_id, work_date=day.isoformat())
        await callback.message.edit_text(
            (
                f"На дату {day.strftime('%d.%m.%Y')} есть активные заявки: {len(result['affected'])}.\n"
                "Если подтвердить удаление, все эти записи будут отменены и клиенты получат уведомления."
            ),
            reply_markup=window_delete_confirm_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "Дата расписания удалена." if result["removed"] else "Не удалось удалить дату.",
        reply_markup=admin_schedule_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:window:delete:abort")
async def admin_window_delete_abort(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Удаление даты отменено.", reply_markup=admin_schedule_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:window:delete:force")
async def admin_window_delete_force(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    data = await state.get_data()
    city_id = int(data.get("city_id", 0))
    raw_day = data.get("work_date")
    if not city_id or not raw_day:
        await callback.answer("Подтверждение устарело", show_alert=True)
        return

    day = datetime.strptime(raw_day, "%Y-%m-%d").date()
    result = await db.delete_working_window_cascade(city_id, day, force=True)
    for row in result["affected"]:
        await callback.bot.send_message(
            row["user_tg_id"],
            (
                f"Ваша запись #{row['id']} отменена администратором.\n"
                "Причина: дата была удалена из расписания.\n"
                f"{row['city_name']} {row['booking_date'].strftime('%d.%m.%Y')}\n"
                f"Часы: {format_slots(row['hours'])}"
            ),
        )
    await state.clear()
    if result["removed"]:
        await callback.message.edit_text(
            f"Дата удалена. Отменено заявок: {len(result['affected'])}",
            reply_markup=admin_schedule_menu_kb(),
        )
    else:
        await callback.message.edit_text("Не удалось удалить дату.", reply_markup=admin_schedule_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:add_block")
async def admin_add_block_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    cities = await db.list_cities()
    if not cities:
        await callback.message.edit_text("Нет городов. Сначала добавьте город.")
        await callback.answer()
        return
    await state.set_state(AdminBlockState.waiting_city)
    await callback.message.edit_text(
        "Город для блокировки",
        reply_markup=cities_kb(cities, "adminblock", "admin:menu:schedule"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminblock:city:"))
async def admin_add_block_city(callback: CallbackQuery, state: FSMContext) -> None:
    city_id = int(callback.data.split(":")[-1])
    await state.update_data(city_id=city_id, month_offset=0)
    await state.set_state(AdminBlockState.waiting_date)
    await callback.message.edit_text(
        "Выберите месяц блокировки",
        reply_markup=admin_months_kb("adminblock", 0, "admin:add_block"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminblock:monthpage:"))
async def admin_block_month_page(callback: CallbackQuery, state: FSMContext) -> None:
    offset = int(callback.data.split(":")[-1])
    await state.update_data(month_offset=offset)
    await callback.message.edit_reply_markup(
        reply_markup=admin_months_kb("adminblock", offset, "admin:add_block")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminblock:month:"))
async def admin_block_month(callback: CallbackQuery, state: FSMContext) -> None:
    ym = callback.data.split(":")[-1]
    year, month = [int(x) for x in ym.split("-")]
    await state.update_data(selected_month=ym)
    await callback.message.edit_text(
        f"Выберите день {month:02d}.{year}",
        reply_markup=admin_days_in_month_kb("adminblock", year, month, "admin:add_block"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminblock:day:"))
async def admin_block_day(callback: CallbackQuery, state: FSMContext) -> None:
    block_date = callback.data.split(":")[-1]
    await state.update_data(block_date=block_date)
    await state.set_state(AdminBlockState.waiting_hours)
    await callback.message.edit_text(
        "Выберите начало интервала",
        reply_markup=admin_start_hour_kb("adminblock", "admin:add_block"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminblock:start:"))
async def admin_block_start_hour(callback: CallbackQuery, state: FSMContext) -> None:
    start_hour = int(callback.data.split(":")[-1])
    await state.update_data(start_hour=start_hour)
    await callback.message.edit_text(
        "Выберите окончание интервала",
        reply_markup=admin_end_hour_kb("adminblock", start_hour, "admin:add_block"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminblock:end:"))
async def admin_block_end_hour(callback: CallbackQuery, state: FSMContext) -> None:
    end_hour = int(callback.data.split(":")[-1])
    data = await state.get_data()
    await state.update_data(end_hour=end_hour)
    await state.set_state(AdminBlockState.waiting_reason)
    await callback.message.edit_text(
        (
            f"Выбрано: {data['start_hour']:02d}:00-{end_hour:02d}:00\n"
            "Введите причину блокировки текстом"
        ),
        reply_markup=simple_back_kb("admin:add_block"),
    )
    await callback.answer()


@router.message(AdminBlockState.waiting_date)
async def admin_add_block_date(message: Message, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin_message(message, db):
        return
    try:
        day = _parse_date(message.text)
    except Exception:
        await message.answer("Неверная дата")
        return
    await state.update_data(block_date=day.isoformat())
    await state.set_state(AdminBlockState.waiting_hours)
    await message.answer("Введите диапазон часов блокировки, пример 13-15")


@router.message(AdminBlockState.waiting_hours)
async def admin_add_block_hours(message: Message, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin_message(message, db):
        return
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
    if not await _ensure_admin_message(message, db):
        return
    data = await state.get_data()
    affected = await db.add_time_block(
        city_id=int(data["city_id"]),
        block_date=_parse_date(data["block_date"]),
        start_hour=int(data["start_hour"]),
        end_hour=int(data["end_hour"]),
        reason=message.text.strip(),
        created_by=message.from_user.id,
    )
    for row in affected:
        await message.bot.send_message(
            row["user_tg_id"],
            (
                f"Ваша запись #{row['id']} отменена администратором.\n"
                "Причина: часы были убраны из расписания.\n"
                f"{row['city_name']} {row['booking_date'].strftime('%d.%m.%Y')}\n"
                f"Часы: {format_slots(row['hours'])}"
            ),
        )
    await state.clear()
    await message.answer(
        f"Блокировка сохранена. Отменено заявок: {len(affected)}",
        reply_markup=admin_schedule_menu_kb(),
    )


@router.callback_query(F.data == "admin:pending")
async def admin_pending_list(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    rows = await db.pending_bookings()
    if not rows:
        await callback.message.edit_text("Нет заявок на подтверждение.")
        await callback.answer()
        return

    for row in rows:
        client_link = _client_link(row["username"], row["user_tg_id"])
        txt = (
            f"Заявка #{row['id']}\n"
            f"Клиент: {client_link}\n"
            f"Город: {row['city_name']}\n"
            f"Дата: {row['booking_date'].strftime('%d.%m.%Y')}\n"
            f"Часы: {format_slots(row['hours'])}\n"
            f"Контакт: {row['tg_contact']}\n"
            f"Имя: {row['client_name'] or '-'}\n"
            f"Телефон: {row['phone'] or '-'}\n"
            f"Тип съемки: {row['shoot_type'] or '-'}\n"
            f"Комментарий: {row['comment'] or '-'}\n"
            f"Итог: {row['total_price']} {row['currency']}"
        )
        await callback.message.answer(txt, reply_markup=pending_action_kb(row["id"]))
    await callback.message.edit_text("Действия с записями", reply_markup=admin_bookings_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:active")
async def admin_active_list(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return

    rows = await db.active_bookings()
    if not rows:
        await callback.message.edit_text("Сейчас нет активных заявок.")
        await callback.answer()
        return

    for row in rows:
        client_link = _client_link(row["username"], row["user_tg_id"])
        txt = (
            f"Заявка #{row['id']} [{row['status']}]\n"
            f"Клиент: {client_link}\n"
            f"Город: {row['city_name']}\n"
            f"Дата: {row['booking_date'].strftime('%d.%m.%Y')}\n"
            f"Часы: {format_slots(row['hours'])}\n"
            f"Контакт: {row['tg_contact']}\n"
            f"Итог: {row['total_price']} {row['currency']}"
        )
        if row["status"] in ("pending", "confirmed"):
            await callback.message.answer(txt, reply_markup=admin_active_action_kb(row["id"]))
        else:
            await callback.message.answer(txt)

    await callback.message.edit_text("Действия с записями", reply_markup=admin_bookings_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:cancel:"))
async def admin_cancel_booking(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    booking_id = int(callback.data.split(":")[-1])
    result = await db.delete_booking_cascade(booking_id)
    booking = result["booking"]
    if not result["deleted"] or not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    await callback.bot.send_message(
        booking["user_tg_id"],
        (
            f"Запись #{booking_id} удалена администратором.\n"
            f"{booking['city_name']} {booking['booking_date'].strftime('%d.%m.%Y')}\n"
            f"Часы: {format_slots(booking['hours'])}"
        ),
    )
    await callback.message.edit_text("Запись удалена.", reply_markup=admin_bookings_menu_kb())
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
                f"Часы: {format_slots(booking['hours'])}\n"
                f"Итог: {booking['total_price']} {booking['currency']}"
            ),
        )
    await callback.message.edit_text(f"Заявка #{booking_id} подтверждена")
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
    await callback.message.edit_text(f"Заявка #{booking_id} отклонена")
    await callback.answer()


@router.callback_query(F.data == "admin:set_price")
async def admin_set_price_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    pricing = await db.get_pricing()
    await state.set_state(AdminPriceState.waiting_hour_price)
    await callback.message.edit_text(
        (
            f"Текущая цена: {pricing['hourly_price']} {pricing['currency']}\n"
            "Введите новую цену за 1 час (целое число, рубли)."
        ),
        reply_markup=simple_back_kb("admin:menu:root"),
    )
    await callback.answer()


@router.message(AdminPriceState.waiting_hour_price)
async def admin_set_price_save(message: Message, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin_message(message, db):
        return
    try:
        price = _parse_price(message.text)
    except Exception:
        await message.answer("Введите корректную цену, например 5000")
        return

    await db.set_pricing(price, message.from_user.id)
    await state.clear()
    await message.answer(format_price_offer(price, "RUB"), reply_markup=admin_menu_kb())


@router.message(Command("archive_now"))
async def cmd_archive_now(message: Message, db: Database, settings) -> None:
    if not await db.is_admin(message.from_user.id):
        await message.answer("У вас нет доступа.")
        return
    archived = await db.archive_expired_bookings(settings.timezone, message.from_user.id)
    await message.answer(f"Архивация завершена. Перенесено: {archived}")


@router.callback_query(F.data == "admin:archive:run")
async def admin_archive_run(callback: CallbackQuery, db: Database, settings) -> None:
    if not await _ensure_admin(callback, db):
        return
    archived = await db.archive_expired_bookings(settings.timezone, callback.from_user.id)
    await callback.message.edit_text(
        f"Архивация завершена. Перенесено: {archived}",
        reply_markup=admin_archive_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:archive:list")
async def admin_archive_list(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if not await _ensure_admin(callback, db):
        return
    await state.clear()
    rows = await db.list_archived(limit=15)
    if not rows:
        await callback.message.edit_text("Архив пуст.")
        await callback.answer()
        return

    for row in rows:
        archived_at = row["archived_at"].strftime("%d.%m.%Y %H:%M") if row["archived_at"] else "-"
        await callback.message.answer(
            (
                f"Архив #{row['id']}\n"
                f"{row['city_name']} {row['booking_date'].strftime('%d.%m.%Y')}\n"
                f"Часы: {format_slots(row['hours'])}\n"
                f"Итог: {row['total_price']} {row['currency']}\n"
                f"Архивировано: {archived_at}"
            ),
            reply_markup=archived_item_kb(row["id"]),
        )
    await callback.message.edit_text("Действия с архивом", reply_markup=admin_archive_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:archive:download:"))
async def admin_archive_download(callback: CallbackQuery, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    booking_id = int(callback.data.split(":")[-1])
    row = await db.get_archive_snapshot(booking_id)
    if not row:
        await callback.answer("Снимок не найден", show_alert=True)
        return

    payload = json.dumps(row["snapshot"], ensure_ascii=False, indent=2).encode("utf-8")
    file = BufferedInputFile(payload, filename=f"archive_booking_{booking_id}.json")
    await callback.message.answer_document(file, caption=f"Архив заявки #{booking_id}")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:archive:delete:"))
async def admin_archive_delete_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    booking_id = int(callback.data.split(":")[-1])
    await state.set_state(AdminArchiveState.waiting_delete_confirmation)
    await state.update_data(delete_booking_id=booking_id)
    await callback.message.edit_text(
        f"Удалить архивный снимок #{booking_id}? Это действие необратимо.",
        reply_markup=archive_delete_confirm_kb(booking_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:archive:confirm_delete:"))
async def admin_archive_delete_confirm(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not await _ensure_admin(callback, db):
        return
    booking_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    if int(data.get("delete_booking_id", 0)) != booking_id:
        await callback.answer("Подтверждение устарело", show_alert=True)
        return

    deleted = await db.delete_archive_snapshot(booking_id)
    await state.clear()
    if deleted:
        await callback.message.edit_text(f"Архивный снимок #{booking_id} удален.")
    else:
        await callback.message.edit_text("Архивный снимок не найден.")
    await callback.answer()


def register_admin_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)