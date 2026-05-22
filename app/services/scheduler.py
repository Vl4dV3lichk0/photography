from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import Settings
from app.db import Database
from app.texts import format_slots


async def _send_reminders(bot: Bot, db: Database) -> None:
    for hours_before in (24, 2):
        rows = await db.due_reminders(hours_before)
        for row in rows:
            text = (
                f"Напоминание: фотосессия через {hours_before} ч.\n"
                f"{row['city_name']} {row['booking_date'].strftime('%d.%m.%Y')}\n"
                f"Часы: {format_slots(row['hours'])}"
            )
            await bot.send_message(row["user_tg_id"], text)
            await db.mark_notified(f"reminder_{hours_before}", row["id"], row["user_tg_id"])


async def _send_daily_summary(bot: Bot, db: Database, settings: Settings) -> None:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    if now.hour != 20:
        return

    target_date = (now + timedelta(days=1)).date()
    rows = await db.daily_summary_for_admins(target_date)
    if rows:
        body = [f"Сводка на {target_date.strftime('%d.%m.%Y')}"]
        for row in rows:
            body.append(
                f"- #{row['id']} {row['city_name']} {format_slots(row['hours'])} ({row['status']})"
            )
        text = "\n".join(body)
    else:
        text = f"На {target_date.strftime('%d.%m.%Y')} записей пока нет."

    for admin_id in await db.active_admin_ids():
        if await db.already_sent_daily(admin_id, target_date):
            continue
        await bot.send_message(admin_id, text)
        await db.mark_notified(f"daily_summary_{target_date.isoformat()}", 0, admin_id)


async def notifications_loop(bot: Bot, db: Database, settings: Settings) -> None:
    while True:
        try:
            await db.archive_expired_bookings(settings.timezone)
            await _send_reminders(bot, db)
            await _send_daily_summary(bot, db, settings)
        except Exception as exc:
            logging.exception("Scheduler error: %s", exc)
        await asyncio.sleep(60)