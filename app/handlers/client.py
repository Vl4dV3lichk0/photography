from __future__ import annotations

from collections import defaultdict
from datetime import date

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import BookingDraft, Database
from app.keyboards import (
    cancel_my_booking_kb,
    cities_kb,
    consent_kb,
    hours_kb,
    main_menu_kb,
    months_kb,
    days_kb,
)
from app.states import ClientBookingState
from app.texts import POLICY_TEXT, format_hours

router = Router()


def _parse_iso_day(raw: str) -> date:
    return date.fromisoformat(raw)


def _is_consecutive(hours: list[int]) -> bool:
    if not hours:
        return False
    ordered = sorted(hours)
    return all((ordered[i + 1] - ordered[i]) == 1 for i in range(len(ordered) - 1))


async def _show_my_bookings(message: Message, db: Database) -> None:
    rows = await db.user_bookings(message.from_user.id)
    if not rows:
        await message.answer("У вас пока нет записей.", reply_markup=main_menu_kb())
        return

    for row in rows:
        txt = (
            f"Запись #{row['id']}\n"
            f"Статус: {row['status']}\n"
            f"{row['city_name']} {row['booking_date'].strftime('%d.%m.%Y')}\n"
            f"Часы: {format_hours(row['hours'])}"
        )
        if row["status"] in ("pending", "confirmed"):
            await message.answer(txt, reply_markup=cancel_my_booking_kb(row["id"]))
        else:
            await message.answer(txt)


@router.message(Command("my"))
async def cmd_my(message: Message, db: Database) -> None:
    await _show_my_bookings(message, db)


@router.callback_query(F.data == "book:my")
async def cb_my(callback: CallbackQuery, db: Database) -> None:
    await _show_my_bookings(callback.message, db)
    await callback.answer()


@router.callback_query(F.data == "book:start")
async def book_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    cities = await db.list_cities()
    if not cities:
        await callback.message.answer("Пока нет активных городов. Попробуйте позже.")
        await callback.answer()
        return

    await state.clear()
    await state.set_state(ClientBookingState.waiting_city)
    await callback.message.answer("Выберите город", reply_markup=cities_kb(cities, "book"))
    await callback.answer()


@router.callback_query(F.data.startswith("book:city:"))
async def book_city(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    city_id = int(callback.data.split(":")[-1])
    dates = [row["work_date"] for row in await db.available_dates(city_id)]
    if not dates:
        await callback.message.answer("По этому городу пока нет дат.")
        await callback.answer()
        return

    await state.update_data(city_id=city_id)
    await state.set_state(ClientBookingState.waiting_month)
    await callback.message.answer("Выберите месяц", reply_markup=months_kb(dates))
    await callback.answer()


@router.callback_query(F.data == "book:back:cities")
async def back_to_cities(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    cities = await db.list_cities()
    await state.set_state(ClientBookingState.waiting_city)
    await callback.message.answer("Выберите город", reply_markup=cities_kb(cities, "book"))
    await callback.answer()


@router.callback_query(F.data.startswith("book:month:"))
async def book_month(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    ym = callback.data.split(":")[-1]
    year, month = [int(x) for x in ym.split("-")]

    data = await state.get_data()
    city_id = int(data["city_id"])
    rows = await db.available_dates(city_id)
    days = [r["work_date"] for r in rows if r["work_date"].year == year and r["work_date"].month == month]

    if not days:
        await callback.answer("В этом месяце свободных дней нет", show_alert=True)
        return

    await state.set_state(ClientBookingState.waiting_day)
    await callback.message.answer("Выберите день", reply_markup=days_kb(days))
    await callback.answer()


@router.callback_query(F.data == "book:back:months")
async def back_to_months(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    city_id = int(data["city_id"])
    dates = [row["work_date"] for row in await db.available_dates(city_id)]
    await state.set_state(ClientBookingState.waiting_month)
    await callback.message.answer("Выберите месяц", reply_markup=months_kb(dates))
    await callback.answer()


@router.callback_query(F.data.startswith("book:day:"))
async def book_day(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    day = _parse_iso_day(callback.data.split(":")[-1])
    data = await state.get_data()
    city_id = int(data["city_id"])
    free_hours = await db.available_hours(city_id, day)
    if not free_hours:
        await callback.answer("На этот день свободных часов нет", show_alert=True)
        return

    await state.update_data(day=day.isoformat(), selected_hours=[])
    await state.set_state(ClientBookingState.waiting_hours)
    await callback.message.answer("Выберите один или несколько часов подряд", reply_markup=hours_kb(free_hours, []))
    await callback.answer()


@router.callback_query(F.data == "book:back:days")
async def back_to_days(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    city_id = int(data["city_id"])
    rows = await db.available_dates(city_id)
    grouped = defaultdict(list)
    for row in rows:
        day = row["work_date"]
        grouped[(day.year, day.month)].append(day)
    last_month = next(iter(grouped.values()), [])
    await state.set_state(ClientBookingState.waiting_day)
    await callback.message.answer("Выберите день", reply_markup=days_kb(last_month))
    await callback.answer()


@router.callback_query(F.data.startswith("book:hour:"))
async def book_toggle_hour(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    hour = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = list(data.get("selected_hours", []))
    if hour in selected:
        selected.remove(hour)
    else:
        selected.append(hour)

    city_id = int(data["city_id"])
    day = _parse_iso_day(data["day"])
    free_hours = await db.available_hours(city_id, day)
    await state.update_data(selected_hours=selected)
    await callback.message.edit_reply_markup(reply_markup=hours_kb(free_hours, selected))
    await callback.answer()


@router.callback_query(F.data == "book:hours:reset")
async def book_reset_hours(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    city_id = int(data["city_id"])
    day = _parse_iso_day(data["day"])
    free_hours = await db.available_hours(city_id, day)
    await state.update_data(selected_hours=[])
    await callback.message.edit_reply_markup(reply_markup=hours_kb(free_hours, []))
    await callback.answer("Выбор часов очищен")


@router.callback_query(F.data == "book:hours:done")
async def book_hours_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = [int(v) for v in data.get("selected_hours", [])]
    if not selected:
        await callback.answer("Выберите хотя бы один слот", show_alert=True)
        return
    if not _is_consecutive(selected):
        await callback.answer("Можно выбрать только часы подряд", show_alert=True)
        return

    await state.set_state(ClientBookingState.waiting_contact)
    await callback.message.answer("Введите Telegram-контакт (@username) или номер")
    await callback.answer()


@router.message(ClientBookingState.waiting_contact)
async def book_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(tg_contact=message.text.strip())
    await state.set_state(ClientBookingState.waiting_name)
    await message.answer("Имя (или '-' чтобы пропустить)")


@router.message(ClientBookingState.waiting_name)
async def book_name(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(client_name=None if value == "-" else value)
    await state.set_state(ClientBookingState.waiting_phone)
    await message.answer("Телефон (или '-' чтобы пропустить)")


@router.message(ClientBookingState.waiting_phone)
async def book_phone(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(phone=None if value == "-" else value)
    await state.set_state(ClientBookingState.waiting_shoot_type)
    await message.answer("Тип съемки (или '-' чтобы пропустить)")


@router.message(ClientBookingState.waiting_shoot_type)
async def book_shoot_type(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(shoot_type=None if value == "-" else value)
    await state.set_state(ClientBookingState.waiting_comment)
    await message.answer("Комментарий (или '-' чтобы пропустить)")


@router.message(ClientBookingState.waiting_comment)
async def book_comment(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(comment=None if value == "-" else value)
    await state.set_state(ClientBookingState.waiting_consent)
    await message.answer(POLICY_TEXT, reply_markup=consent_kb())


@router.callback_query(F.data == "book:consent:no")
async def book_consent_no(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Заявка отменена.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "book:consent:yes")
async def book_consent_yes(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    data = await state.get_data()
    try:
        draft = BookingDraft(
            user_tg_id=callback.from_user.id,
            username=callback.from_user.username,
            city_id=int(data["city_id"]),
            booking_date=_parse_iso_day(data["day"]),
            hours=sorted([int(h) for h in data["selected_hours"]]),
            tg_contact=data["tg_contact"],
            client_name=data.get("client_name"),
            phone=data.get("phone"),
            shoot_type=data.get("shoot_type"),
            comment=data.get("comment"),
            policy_version=settings.policy_version,
        )
        booking_id = await db.create_booking(draft)
    except Exception as exc:
        await callback.message.answer(f"Не удалось создать заявку: {exc}")
        await callback.answer()
        return

    city = await db.get_city(draft.city_id)
    await callback.message.answer(
        (
            f"Заявка #{booking_id} создана и отправлена на подтверждение.\n"
            f"{city['name']} {draft.booking_date.strftime('%d.%m.%Y')}\n"
            f"Часы: {format_hours(draft.hours)}"
        ),
        reply_markup=main_menu_kb(),
    )

    for admin_id in await db.active_admin_ids():
        await callback.bot.send_message(
            admin_id,
            (
                f"Новая заявка #{booking_id}\n"
                f"Город: {city['name']}\n"
                f"Дата: {draft.booking_date.strftime('%d.%m.%Y')}\n"
                f"Часы: {format_hours(draft.hours)}\n"
                "Откройте /admin -> Заявки на подтверждение"
            ),
        )

    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("book:cancel:"))
async def book_cancel(callback: CallbackQuery, db: Database) -> None:
    booking_id = int(callback.data.split(":")[-1])
    booking = await db.get_booking(booking_id)
    if not booking or booking["user_tg_id"] != callback.from_user.id:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    ok = await db.cancel_booking(booking_id, callback.from_user.id)
    if not ok:
        await callback.answer("Запись уже неактивна", show_alert=True)
        return

    await callback.message.answer(f"Запись #{booking_id} отменена")
    for admin_id in await db.active_admin_ids():
        await callback.bot.send_message(
            admin_id,
            (
                f"Клиент отменил запись #{booking_id}\n"
                f"{booking['city_name']} {booking['booking_date'].strftime('%d.%m.%Y')}\n"
                f"Часы: {format_hours(booking['hours'])}"
            ),
        )
    await callback.answer()


def register_client_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)