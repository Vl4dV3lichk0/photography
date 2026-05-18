from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

import asyncpg


@dataclass(slots=True)
class BookingDraft:
    user_tg_id: int
    username: Optional[str]
    city_id: int
    booking_date: date
    hours: List[int]
    tg_contact: str
    client_name: Optional[str]
    phone: Optional[str]
    shoot_type: Optional[str]
    comment: Optional[str]
    policy_version: str


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=8)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def init_schema(self) -> None:
        if not self.pool:
            raise RuntimeError("Database pool is not initialized")

        sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        async with self.pool.acquire() as conn:
            await conn.execute(sql)

    async def seed_admins(self, admin_ids: Sequence[int], owner_tg_id: int) -> None:
        if not self.pool:
            raise RuntimeError("Database pool is not initialized")

        async with self.pool.acquire() as conn:
            for admin_id in admin_ids:
                await conn.execute(
                    """
                    INSERT INTO admins (tg_id, added_by)
                    VALUES ($1, $2)
                    ON CONFLICT (tg_id) DO NOTHING
                    """,
                    admin_id,
                    owner_tg_id,
                )

    async def is_admin(self, tg_id: int) -> bool:
        if not self.pool:
            return False
        row = await self.pool.fetchrow("SELECT 1 FROM admins WHERE tg_id = $1", tg_id)
        return bool(row)

    async def add_city(self, name: str) -> None:
        await self.pool.execute(
            """
            INSERT INTO cities (name)
            VALUES ($1)
            ON CONFLICT (name) DO NOTHING
            """,
            name.strip(),
        )

    async def list_cities(self) -> List[asyncpg.Record]:
        return await self.pool.fetch(
            "SELECT id, name FROM cities WHERE is_active = TRUE ORDER BY name"
        )

    async def get_city(self, city_id: int) -> Optional[asyncpg.Record]:
        return await self.pool.fetchrow(
            "SELECT id, name FROM cities WHERE id = $1 AND is_active = TRUE", city_id
        )

    async def set_working_window(
        self, city_id: int, work_date: date, start_hour: int, end_hour: int, created_by: int
    ) -> tuple[bool, str]:
        other_city = await self.pool.fetchrow(
            """
            SELECT c.name
            FROM working_windows ww
            JOIN cities c ON c.id = ww.city_id
            WHERE ww.work_date = $1 AND ww.city_id <> $2
            LIMIT 1
            """,
            work_date,
            city_id,
        )
        if other_city:
            return False, f"На дату уже стоит город: {other_city['name']}"

        await self.pool.execute(
            """
            INSERT INTO working_windows (city_id, work_date, start_hour, end_hour, created_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (city_id, work_date)
            DO UPDATE SET
                start_hour = EXCLUDED.start_hour,
                end_hour = EXCLUDED.end_hour,
                created_by = EXCLUDED.created_by,
                created_at = NOW()
            """,
            city_id,
            work_date,
            start_hour,
            end_hour,
            created_by,
        )
        return True, "Расписание сохранено"

    async def add_time_block(
        self,
        city_id: int,
        block_date: date,
        start_hour: int,
        end_hour: int,
        reason: str,
        created_by: int,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO time_blocks (city_id, block_date, start_hour, end_hour, reason, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            city_id,
            block_date,
            start_hour,
            end_hour,
            reason,
            created_by,
        )

    async def available_dates(self, city_id: int) -> List[asyncpg.Record]:
        return await self.pool.fetch(
            """
            SELECT work_date, start_hour, end_hour
            FROM working_windows
            WHERE city_id = $1 AND work_date >= CURRENT_DATE
            ORDER BY work_date
            """,
            city_id,
        )

    async def available_hours(self, city_id: int, day: date) -> List[int]:
        window = await self.pool.fetchrow(
            """
            SELECT start_hour, end_hour
            FROM working_windows
            WHERE city_id = $1 AND work_date = $2
            """,
            city_id,
            day,
        )
        if not window:
            return []

        blocked_rows = await self.pool.fetch(
            """
            SELECT start_hour, end_hour
            FROM time_blocks
            WHERE city_id = $1 AND block_date = $2
            """,
            city_id,
            day,
        )
        blocked_hours = set()
        for row in blocked_rows:
            blocked_hours.update(range(row["start_hour"], row["end_hour"]))

        busy_rows = await self.pool.fetch(
            """
            SELECT hour
            FROM booking_slots bs
            JOIN bookings b ON b.id = bs.booking_id
            WHERE bs.city_id = $1 AND bs.slot_date = $2
              AND b.status IN ('pending', 'confirmed')
            """,
            city_id,
            day,
        )
        busy_hours = {int(row["hour"]) for row in busy_rows}

        all_hours = range(window["start_hour"], window["end_hour"])
        free = [hour for hour in all_hours if hour not in blocked_hours and hour not in busy_hours]
        return free

    async def create_booking(self, draft: BookingDraft) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                free_hours = await self.available_hours(draft.city_id, draft.booking_date)
                if not set(draft.hours).issubset(set(free_hours)):
                    raise ValueError("Часть выбранных часов уже недоступна")

                booking_id = await conn.fetchval(
                    """
                    INSERT INTO bookings (
                        user_tg_id, username, city_id, booking_date, status,
                        tg_contact, client_name, phone, shoot_type, comment,
                        policy_version, consent_accepted
                    ) VALUES (
                        $1, $2, $3, $4, 'pending',
                        $5, $6, $7, $8, $9,
                        $10, TRUE
                    )
                    RETURNING id
                    """,
                    draft.user_tg_id,
                    draft.username,
                    draft.city_id,
                    draft.booking_date,
                    draft.tg_contact,
                    draft.client_name,
                    draft.phone,
                    draft.shoot_type,
                    draft.comment,
                    draft.policy_version,
                )

                for hour in sorted(draft.hours):
                    await conn.execute(
                        """
                        INSERT INTO booking_slots (booking_id, city_id, slot_date, hour)
                        VALUES ($1, $2, $3, $4)
                        """,
                        booking_id,
                        draft.city_id,
                        draft.booking_date,
                        hour,
                    )

                await conn.execute(
                    "INSERT INTO consents (user_tg_id, policy_version) VALUES ($1, $2)",
                    draft.user_tg_id,
                    draft.policy_version,
                )
                await conn.execute(
                    """
                    INSERT INTO booking_events_audit (booking_id, event_type, actor_tg_id, payload)
                    VALUES ($1, 'booking_created', $2, jsonb_build_object('hours', $3::jsonb))
                    """,
                    booking_id,
                    draft.user_tg_id,
                    str(draft.hours),
                )
        return int(booking_id)

    async def pending_bookings(self) -> List[asyncpg.Record]:
        return await self.pool.fetch(
            """
            SELECT b.id, b.user_tg_id, b.username, b.booking_date, b.client_name, b.phone,
                   b.shoot_type, b.comment, b.tg_contact, c.name AS city_name,
                   ARRAY_AGG(bs.hour ORDER BY bs.hour) AS hours
            FROM bookings b
            JOIN cities c ON c.id = b.city_id
            JOIN booking_slots bs ON bs.booking_id = b.id
            WHERE b.status = 'pending'
            GROUP BY b.id, c.name
            ORDER BY b.created_at
            """
        )

    async def update_booking_status(self, booking_id: int, status: str, admin_tg_id: int) -> bool:
        row = await self.pool.fetchrow(
            """
            UPDATE bookings
            SET status = $2, confirmed_by = $3, updated_at = NOW()
            WHERE id = $1 AND status = 'pending'
            RETURNING user_tg_id
            """,
            booking_id,
            status,
            admin_tg_id,
        )
        if not row:
            return False

        await self.pool.execute(
            """
            INSERT INTO booking_events_audit (booking_id, event_type, actor_tg_id)
            VALUES ($1, $2, $3)
            """,
            booking_id,
            f"booking_{status}",
            admin_tg_id,
        )
        return True

    async def get_booking(self, booking_id: int) -> Optional[asyncpg.Record]:
        return await self.pool.fetchrow(
            """
            SELECT b.id, b.user_tg_id, b.status, b.booking_date, c.name AS city_name,
                   ARRAY_AGG(bs.hour ORDER BY bs.hour) AS hours
            FROM bookings b
            JOIN cities c ON c.id = b.city_id
            JOIN booking_slots bs ON bs.booking_id = b.id
            WHERE b.id = $1
            GROUP BY b.id, c.name
            """,
            booking_id,
        )

    async def cancel_booking(self, booking_id: int, actor_tg_id: int) -> bool:
        row = await self.pool.fetchrow(
            """
            UPDATE bookings
            SET status = 'canceled', updated_at = NOW()
            WHERE id = $1 AND status IN ('pending', 'confirmed')
            RETURNING user_tg_id
            """,
            booking_id,
        )
        if not row:
            return False
        await self.pool.execute(
            """
            INSERT INTO booking_events_audit (booking_id, event_type, actor_tg_id)
            VALUES ($1, 'booking_canceled', $2)
            """,
            booking_id,
            actor_tg_id,
        )
        return True

    async def user_bookings(self, user_tg_id: int) -> List[asyncpg.Record]:
        return await self.pool.fetch(
            """
            SELECT b.id, b.status, b.booking_date, c.name AS city_name,
                   ARRAY_AGG(bs.hour ORDER BY bs.hour) AS hours
            FROM bookings b
            JOIN cities c ON c.id = b.city_id
            JOIN booking_slots bs ON bs.booking_id = b.id
            WHERE b.user_tg_id = $1
            GROUP BY b.id, c.name
            ORDER BY b.booking_date DESC
            LIMIT 20
            """,
            user_tg_id,
        )

    async def schedule_preview(self, days: int = 21, limit: int = 15) -> List[asyncpg.Record]:
        return await self.pool.fetch(
            """
            WITH windows AS (
                SELECT ww.city_id, ww.work_date, ww.start_hour, ww.end_hour
                FROM working_windows ww
                WHERE ww.work_date BETWEEN CURRENT_DATE AND CURRENT_DATE + $1::int
            ),
            possible_hours AS (
                SELECT w.city_id, w.work_date, gs.hour::int AS hour
                FROM windows w
                CROSS JOIN LATERAL generate_series(w.start_hour, w.end_hour - 1) AS gs(hour)
            ),
            blocked_hours AS (
                SELECT tb.city_id, tb.block_date AS work_date, gs.hour::int AS hour
                FROM time_blocks tb
                JOIN windows w ON w.city_id = tb.city_id AND w.work_date = tb.block_date
                CROSS JOIN LATERAL generate_series(tb.start_hour, tb.end_hour - 1) AS gs(hour)
            ),
            busy_hours AS (
                SELECT bs.city_id, bs.slot_date AS work_date, bs.hour::int AS hour
                FROM booking_slots bs
                JOIN bookings b ON b.id = bs.booking_id
                JOIN windows w ON w.city_id = bs.city_id AND w.work_date = bs.slot_date
                WHERE b.status IN ('pending', 'confirmed')
            )
            SELECT c.name AS city_name,
                   p.city_id,
                   p.work_date,
                   ARRAY_AGG(p.hour ORDER BY p.hour) AS free_hours
            FROM possible_hours p
            JOIN cities c ON c.id = p.city_id
            LEFT JOIN blocked_hours bh
              ON bh.city_id = p.city_id AND bh.work_date = p.work_date AND bh.hour = p.hour
            LEFT JOIN busy_hours byh
              ON byh.city_id = p.city_id AND byh.work_date = p.work_date AND byh.hour = p.hour
            WHERE bh.hour IS NULL
              AND byh.hour IS NULL
            GROUP BY c.name, p.city_id, p.work_date
            ORDER BY p.work_date, c.name
            LIMIT $2
            """,
            days,
            limit,
        )

    async def due_reminders(self, hours_before: int) -> List[asyncpg.Record]:
        return await self.pool.fetch(
            """
            WITH grouped AS (
                SELECT b.id, b.user_tg_id, b.booking_date, c.name AS city_name,
                       ARRAY_AGG(bs.hour ORDER BY bs.hour) AS hours,
                       MIN(bs.hour) AS first_hour
                FROM bookings b
                JOIN cities c ON c.id = b.city_id
                JOIN booking_slots bs ON bs.booking_id = b.id
                WHERE b.status = 'confirmed'
                GROUP BY b.id, c.name
            )
            SELECT g.id, g.user_tg_id, g.booking_date, g.city_name, g.hours
            FROM grouped g
            WHERE (g.booking_date + (g.first_hour || ' hour')::interval)
                    BETWEEN NOW() + ($1::text || ' hour')::interval - interval '6 minutes'
                        AND NOW() + ($1::text || ' hour')::interval + interval '6 minutes'
              AND NOT EXISTS (
                SELECT 1 FROM notification_log nl
                WHERE nl.kind = ('reminder_' || $1::text)
                  AND nl.ref_id = g.id
                  AND nl.sent_to = g.user_tg_id
              )
            """,
            hours_before,
        )

    async def mark_notified(self, kind: str, ref_id: int, sent_to: int) -> None:
        await self.pool.execute(
            """
            INSERT INTO notification_log (kind, ref_id, sent_to)
            VALUES ($1, $2, $3)
            ON CONFLICT (kind, ref_id, sent_to) DO NOTHING
            """,
            kind,
            ref_id,
            sent_to,
        )

    async def daily_summary_for_admins(self, target_date: date) -> List[asyncpg.Record]:
        return await self.pool.fetch(
            """
            SELECT b.id, b.status, b.booking_date, c.name AS city_name,
                   b.user_tg_id, ARRAY_AGG(bs.hour ORDER BY bs.hour) AS hours
            FROM bookings b
            JOIN cities c ON c.id = b.city_id
            JOIN booking_slots bs ON bs.booking_id = b.id
            WHERE b.booking_date = $1
              AND b.status IN ('pending', 'confirmed')
            GROUP BY b.id, c.name
            ORDER BY c.name, MIN(bs.hour)
            """,
            target_date,
        )

    async def already_sent_daily(self, admin_tg_id: int, target_date: date) -> bool:
        row = await self.pool.fetchrow(
            """
            SELECT 1
            FROM notification_log
            WHERE kind = $1 AND sent_to = $2
            LIMIT 1
            """,
            f"daily_summary_{target_date.isoformat()}",
            admin_tg_id,
        )
        return bool(row)

    async def active_admin_ids(self) -> List[int]:
        rows = await self.pool.fetch("SELECT tg_id FROM admins")
        return [int(r["tg_id"]) for r in rows]
