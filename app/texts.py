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
        return "Пока нет доступных окон для записи."

    chunks = ["Ближайшие доступные даты (до 15 записей):"]
    for row in rows:
        day: date = row["work_date"]
        chunks.append(
            f"- {row['city_name']}: {day.strftime('%d.%m')} {format_hour_ranges(row['free_hours'])}"
        )
    return "\n".join(chunks)