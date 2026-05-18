from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable, List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Записаться", callback_data="book:start")
    kb.button(text="Прайс", callback_data="info:price")
    kb.button(text="Мои записи", callback_data="book:my")
    kb.adjust(1)
    return kb.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Добавить город", callback_data="admin:add_city")
    kb.button(text="Установить расписание", callback_data="admin:set_window")
    kb.button(text="Добавить блокировку", callback_data="admin:add_block")
    kb.button(text="Изменить цену за час", callback_data="admin:set_price")
    kb.button(text="Заявки на подтверждение", callback_data="admin:pending")
    kb.button(text="Архивация сейчас", callback_data="admin:archive:run")
    kb.button(text="Архивные записи", callback_data="admin:archive:list")
    kb.adjust(1)
    return kb.as_markup()


def cities_kb(cities: Iterable[dict], prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for city in cities:
        kb.button(text=city["name"], callback_data=f"{prefix}:city:{city['id']}")
    kb.adjust(1)
    return kb.as_markup()


def months_kb(dates: List[date]) -> InlineKeyboardMarkup:
    grouped = defaultdict(int)
    month_names = {
        1: "Январь",
        2: "Февраль",
        3: "Март",
        4: "Апрель",
        5: "Май",
        6: "Июнь",
        7: "Июль",
        8: "Август",
        9: "Сентябрь",
        10: "Октябрь",
        11: "Ноябрь",
        12: "Декабрь",
    }
    for day in dates:
        grouped[(day.year, day.month)] += 1

    kb = InlineKeyboardBuilder()
    for (year, month), count in sorted(grouped.items()):
        kb.button(
            text=f"{month_names[month]} {year} ({count} дн.)",
            callback_data=f"book:month:{year}-{month:02d}",
        )
    kb.button(text="Назад", callback_data="book:back:cities")
    kb.adjust(1)
    return kb.as_markup()


def days_kb(days: List[date]) -> InlineKeyboardMarkup:
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb = InlineKeyboardBuilder()
    for day in days:
        kb.button(
            text=f"{weekdays[day.weekday()]} {day.strftime('%d.%m.%Y')}",
            callback_data=f"book:day:{day.isoformat()}",
        )
    kb.button(text="Назад", callback_data="book:back:months")
    kb.adjust(2)
    return kb.as_markup()


def hours_kb(hours: List[int], selected: List[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    selected_set = set(selected)
    for hour in hours:
        mark = "[x]" if hour in selected_set else "[ ]"
        kb.button(text=f"{mark} {hour:02d}:00 - {hour + 1:02d}:00", callback_data=f"book:hour:{hour}")
    kb.button(text="Подтвердить часы", callback_data="book:hours:done")
    kb.button(text="Сбросить", callback_data="book:hours:reset")
    kb.button(text="Назад", callback_data="book:back:days")
    kb.adjust(3, 1, 2)
    return kb.as_markup()


def consent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Согласен", callback_data="book:consent:yes")],
            [InlineKeyboardButton(text="Назад", callback_data="book:back:comment")],
            [InlineKeyboardButton(text="Отмена", callback_data="book:consent:no")],
        ]
    )


def back_only_kb(target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data=f"book:back:{target}")]]
    )


def skip_or_back_kb(target: str, skip_target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data=f"book:skip:{skip_target}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"book:back:{target}")],
        ]
    )


def pending_action_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подтвердить", callback_data=f"admin:approve:{booking_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"admin:reject:{booking_id}"),
            ]
        ]
    )


def cancel_my_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отменить запись", callback_data=f"book:cancel:{booking_id}")]
        ]
    )


def archived_item_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Скачать JSON", callback_data=f"admin:archive:download:{booking_id}"),
                InlineKeyboardButton(text="Удалить", callback_data=f"admin:archive:delete:{booking_id}"),
            ]
        ]
    )


def archive_delete_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подтвердить удаление", callback_data=f"admin:archive:confirm_delete:{booking_id}"),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:archive:list")],
        ]
    )