from __future__ import annotations

from datetime import date
from typing import Iterable


POLICY_TEXT = (
    "Согласие на обработку персональных данных\n\n"
    "Нажимая 'Согласен', вы разрешаете использовать переданные данные "
    "только для организации фотосессии: связи, согласования и ведения записи."
)


def format_hours(hours: Iterable[int]) -> str:
    return ", ".join([f"{hour:02d}:00" for hour in sorted(hours)])


def format_slots(hours: Iterable[int]) -> str:
    return ", ".join([f"{hour:02d}:00-{hour + 1:02d}:00" for hour in sorted(hours)])


def format_hour_ranges(hours: Iterable[int]) -> str:
    ordered = sorted(set(hours))
    if not ordered:
        return "нет свободных часов"

    ranges = []
    start = ordered[0]
    prev = ordered[0]

    for hour in ordered[1:]:
        if hour == prev + 1:
            prev = hour
            continue
        ranges.append((start, prev + 1))
        start = hour
        prev = hour
    ranges.append((start, prev + 1))

    return ", ".join([f"{left:02d}:00-{right:02d}:00" for left, right in ranges])


def format_schedule_preview(rows: list) -> str:
    if not rows:
        return (
            "PHOTOSESSION BOT\n"
            "Пока нет доступных окон для записи.\n"
            "Нажмите 'Прайс' для условий и стоимости."
        )

    chunks = ["PHOTOSESSION BOT", "Ближайшие доступные даты (до 15 записей):"]
    for row in rows:
        day: date = row["work_date"]
        chunks.append(
            f"- {row['city_name']}: {day.strftime('%d.%m')} {format_hour_ranges(row['free_hours'])}"
        )
    return "\n".join(chunks)


def format_price_offer(hourly_price: int, currency: str) -> str:
    return (
        "PHOTOSESSION BOT\n"
        "Прайс и условия\n"
        f"1 час съемки: {hourly_price} {currency}\n"
        "Стоимость фиксируется в момент создания заявки.\n"
        "Предоплата не требуется.\n"
        "Итог = количество выбранных часов x цена за час."
    )


def format_start_message(rows: list, hourly_price: int, currency: str) -> str:
    return f"{format_schedule_preview(rows)}\n\n{format_price_offer(hourly_price, currency)}"