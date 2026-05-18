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


def format_schedule_preview(rows: list) -> str:
    if not rows:
        return "Пока нет опубликованного расписания."

    chunks = ["Ближайшее расписание по городам:"]
    for row in rows:
        day: date = row["work_date"]
        chunks.append(
            f"- {row['city_name']}: {day.strftime('%d.%m')} {row['start_hour']:02d}:00-{row['end_hour']:02d}:00"
        )
    return "\n".join(chunks)