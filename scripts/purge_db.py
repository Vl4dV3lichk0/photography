from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv


TABLES = [
    "booking_events_audit",
    "booking_archive_snapshots",
    "booking_slots",
    "bookings",
    "time_blocks",
    "working_windows",
    "consents",
    "notification_log",
    "cities",
    "admins",
    "pricing_settings",
]


async def main() -> int:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("[FAIL] DATABASE_URL not found in .env")
        return 1

    if "--yes" not in sys.argv:
        print("This will delete ALL records from the database.")
        print("Run with --yes to confirm:")
        print("python scripts/purge_db.py --yes")
        return 1

    conn = await asyncpg.connect(database_url)
    try:
        table_sql = ", ".join(TABLES)
        await conn.execute(f"TRUNCATE TABLE {table_sql} RESTART IDENTITY CASCADE")
        await conn.execute(
            """
            INSERT INTO pricing_settings (id, hourly_price, currency)
            VALUES (1, 5000, 'RUB')
            ON CONFLICT (id) DO NOTHING
            """
        )
        print("[OK] All records were deleted. Schema is preserved.")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))