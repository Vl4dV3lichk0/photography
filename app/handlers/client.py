from __future__ import annotations

from datetime import date

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.db import BookingDraft, Database
from app.keyboards import (
    back_only_kb,
    cancel_my_booking_kb,
    cities_kb,
    consent_kb,
    hours_kb,
    main_menu_kb,
    months_kb,
    days_kb,
    skip_or_back_kb,
)
from app.states import ClientBookingState
from app.texts import POLICY_TEXT, format_slots

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
            f"Часы: {format_slots(row['hours'])}\n"
            f"Итог: {row['total_price']} {row['currency']}"
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
    rows = await db.user_bookings(callback.from_user.id)
    if not rows:
        await callback.message.answer("У вас пока нет записей.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    for row in rows:
        txt = (
            f"Запись #{row['id']}\n"
            f"Статус: {row['status']}\n"
            f"{row['city_name']} {row['booking_date'].strftime('%d.%m.%Y')}\n"
            f"Часы: {format_slots(row['hours'])}\n"
            f"Итог: {row['total_price']} {row['currency']}"
        )
        if row["status"] in ("pending", "confirmed"):
            await callback.message.answer(txt, reply_markup=cancel_my_booking_kb(row["id"]))
        else:
            await callback.message.answer(txt)
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


async def _prompt_contact(message: Message) -> None:
    await message.answer(
        "Введите Telegram-контакт (@username) или номер",
        reply_markup=back_only_kb("hours"),
    )


async def _prompt_name(message: Message) -> None:
    await message.answer("Имя (необязательно)", reply_markup=skip_or_back_kb("contact", "name"))


async def _prompt_phone(message: Message) -> None:
    await message.answer("Телефон (необязательно)", reply_markup=skip_or_back_kb("name", "phone"))


async def _prompt_shoot_type(message: Message) -> None:
    await message.answer(
        "Тип съемки (необязательно)",
        reply_markup=skip_or_back_kb("phone", "shoot_type"),
    )


async def _prompt_comment(message: Message) -> None:
    await message.answer(
        "Комментарий (необязательно)",
        reply_markup=skip_or_back_kb("shoot_type", "comment"),
    )


async def _send_consent_step(message: Message, db: Database, data: dict) -> None:
    selected_hours = [int(v) for v in data.get("selected_hours", [])]
    pricing = await db.get_pricing()
    total = len(selected_hours) * int(pricing["hourly_price"])
    summary = (
        f"Вы выбрали: {format_slots(selected_hours)}\n"
        f"Итог: {total} {pricing['currency']}\n\n"
        f"{POLICY_TEXT}"
    )
    await message.answer(summary, reply_markup=consent_kb())


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
    current_day = _parse_iso_day(data["day"]) if data.get("day") else None
    rows = await db.available_dates(city_id)
    days = [row["work_date"] for row in rows]
    if current_day:
        days = [d for d in days if d.year == current_day.year and d.month == current_day.month]
    await state.set_state(ClientBookingState.waiting_day)
    await callback.message.answer("Выберите день", reply_markup=days_kb(days))
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
async def book_hours_done(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    selected = [int(v) for v in data.get("selected_hours", [])]
    if not selected:
        await callback.answer("Выберите хотя бы один слот", show_alert=True)
        return
    if not _is_consecutive(selected):
        await callback.answer("Можно выбрать только часы подряд", show_alert=True)
        return

    pricing = await db.get_pricing()
    total = len(selected) * int(pricing["hourly_price"])
    await state.set_state(ClientBookingState.waiting_contact)
    await callback.message.answer(
        f"Выбрано часов: {len(selected)}\nПредварительный итог: {total} {pricing['currency']}"
    )
    await _prompt_contact(callback.message)
    await callback.answer()


@router.message(ClientBookingState.waiting_contact)
async def book_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(tg_contact=message.text.strip())
    await state.set_state(ClientBookingState.waiting_name)
    await _prompt_name(message)


@router.message(ClientBookingState.waiting_name)
async def book_name(message: Message, state: FSMContext) -> None:
    await state.update_data(client_name=message.text.strip())
    await state.set_state(ClientBookingState.waiting_phone)
    await _prompt_phone(message)


@router.message(ClientBookingState.waiting_phone)
async def book_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.text.strip())
    await state.set_state(ClientBookingState.waiting_shoot_type)
    await _prompt_shoot_type(message)


@router.message(ClientBookingState.waiting_shoot_type)
async def book_shoot_type(message: Message, state: FSMContext) -> None:
    await state.update_data(shoot_type=message.text.strip())
    await state.set_state(ClientBookingState.waiting_comment)
    await _prompt_comment(message)


@router.message(ClientBookingState.waiting_comment)
async def book_comment(message: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(comment=message.text.strip())
    await state.set_state(ClientBookingState.waiting_consent)
    data = await state.get_data()
    await _send_consent_step(message, db, data)


@router.callback_query(F.data.startswith("book:skip:"))
async def book_skip_optional(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    target = callback.data.split(":")[-1]
    if target == "name":
        await state.update_data(client_name=None)
        await state.set_state(ClientBookingState.waiting_phone)
        await _prompt_phone(callback.message)
    elif target == "phone":
        await state.update_data(phone=None)
        await state.set_state(ClientBookingState.waiting_shoot_type)
        await _prompt_shoot_type(callback.message)
    elif target == "shoot_type":
        await state.update_data(shoot_type=None)
        await state.set_state(ClientBookingState.waiting_comment)
        await _prompt_comment(callback.message)
    elif target == "comment":
        await state.update_data(comment=None)
        await state.set_state(ClientBookingState.waiting_consent)
        data = await state.get_data()
        await _send_consent_step(callback.message, db, data)
    await callback.answer()


@router.callback_query(F.data == "book:back:hours")
async def back_to_hours_from_contact(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    city_id = int(data["city_id"])
    day = _parse_iso_day(data["day"])
    free_hours = await db.available_hours(city_id, day)
    selected = [int(v) for v in data.get("selected_hours", [])]
    await state.set_state(ClientBookingState.waiting_hours)
    await callback.message.answer("Выберите один или несколько часов подряд", reply_markup=hours_kb(free_hours, selected))
    await callback.answer()


@router.callback_query(F.data == "book:back:contact")
async def back_to_contact(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientBookingState.waiting_contact)
    await _prompt_contact(callback.message)
    await callback.answer()


@router.callback_query(F.data == "book:back:name")
async def back_to_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientBookingState.waiting_name)
    await _prompt_name(callback.message)
    await callback.answer()


@router.callback_query(F.data == "book:back:phone")
async def back_to_phone(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientBookingState.waiting_phone)
    await _prompt_phone(callback.message)
    await callback.answer()


@router.callback_query(F.data == "book:back:shoot_type")
async def back_to_shoot_type(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientBookingState.waiting_shoot_type)
    await _prompt_shoot_type(callback.message)
    await callback.answer()


@router.callback_query(F.data == "book:back:comment")
async def back_to_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ClientBookingState.waiting_comment)
    await _prompt_comment(callback.message)
    await callback.answer()


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
        pricing = await db.get_pricing()
        selected_hours = sorted([int(h) for h in data["selected_hours"]])
        draft = BookingDraft(
            user_tg_id=callback.from_user.id,
            username=callback.from_user.username,
            city_id=int(data["city_id"]),
            booking_date=_parse_iso_day(data["day"]),
            hours=selected_hours,
            tg_contact=data["tg_contact"],
            client_name=data.get("client_name"),
            phone=data.get("phone"),
            shoot_type=data.get("shoot_type"),
            comment=data.get("comment"),
            policy_version=settings.policy_version,
            hour_price=int(pricing["hourly_price"]),
            total_price=len(selected_hours) * int(pricing["hourly_price"]),
            currency=pricing["currency"],
        )
        booking_id = await db.create_booking(draft)
    except Exception as exc:
        await callback.message.answer(f"Не удалось создать заявку: {exc}")
        await callback.answer()
        return

    city = await db.get_city(draft.city_id)
    client_link = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else f"<a href=\"tg://user?id={callback.from_user.id}\">Клиент</a>"
    )
    await callback.message.answer(
        (
            f"Заявка #{booking_id} создана и отправлена на подтверждение.\n"
            f"{city['name']} {draft.booking_date.strftime('%d.%m.%Y')}\n"
            f"Часы: {format_slots(draft.hours)}\n"
            f"Итог: {draft.total_price} {draft.currency}"
        ),
        reply_markup=main_menu_kb(),
    )

    for admin_id in await db.active_admin_ids():
        await callback.bot.send_message(
            admin_id,
            (
                f"Новая заявка #{booking_id}\n"
                f"Клиент: {client_link}\n"
                f"Город: {city['name']}\n"
                f"Дата: {draft.booking_date.strftime('%d.%m.%Y')}\n"
                f"Часы: {format_slots(draft.hours)}\n"
                f"Итог: {draft.total_price} {draft.currency}\n"
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
    client_link = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else f"<a href=\"tg://user?id={callback.from_user.id}\">Клиент</a>"
    )
    for admin_id in await db.active_admin_ids():
        await callback.bot.send_message(
            admin_id,
            (
                f"Клиент отменил запись #{booking_id}\n"
                f"Профиль: {client_link}\n"
                f"{booking['city_name']} {booking['booking_date'].strftime('%d.%m.%Y')}\n"
                f"Часы: {format_slots(booking['hours'])}\n"
                f"Итог: {booking['total_price']} {booking['currency']}"
            ),
        )
    await callback.answer()


def register_client_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)