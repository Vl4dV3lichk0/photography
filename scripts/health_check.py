from __future__ import annotations

import asyncio
import json
import os
import sys
from urllib.error import URLError
from urllib.request import urlopen

import asyncpg
from dotenv import load_dotenv


REQUIRED_TABLES = [
    "admins",
    "cities",
    "working_windows",
    "time_blocks",
    "bookings",
    "booking_slots",
    "booking_events_audit",
    "consents",
    "notification_log",
    "booking_archive_snapshots",
    "pricing_settings",
]


def _ok(label: str, details: str = "") -> None:
    print(f"[OK] {label}{': ' + details if details else ''}")


def _fail(label: str, details: str = "") -> None:
    print(f"[FAIL] {label}{': ' + details if details else ''}")


def _warn(label: str, details: str = "") -> None:
    print(f"[WARN] {label}{': ' + details if details else ''}")


def _tg_request(token: str, method: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    with urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


async def _check_db(database_url: str) -> bool:
    try:
        conn = await asyncpg.connect(database_url)
    except Exception as exc:
        _fail("PostgreSQL connection", str(exc))
        return False

    try:
        version = await conn.fetchval("SELECT version()")
        _ok("PostgreSQL connection", version.split(",")[0])

        missing = []
        for table in REQUIRED_TABLES:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = $1
                )
                """,
                table,
            )
            if not exists:
                missing.append(table)

        if missing:
            _fail("Schema", f"Missing tables: {', '.join(missing)}")
            return False

        _ok("Schema", "All required tables are present")

        admins_count = await conn.fetchval("SELECT COUNT(*) FROM admins")
        _ok("Admins seeded", f"{admins_count} rows")
        return True
    finally:
        await conn.close()


async def main() -> int:
    load_dotenv()

    token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not token:
        _fail("BOT_TOKEN", "Not found in .env")
        return 1
    _ok("BOT_TOKEN", "Loaded")

    if not database_url:
        _fail("DATABASE_URL", "Not found in .env")
        return 1
    _ok("DATABASE_URL", "Loaded")

    # Telegram API checks.
    try:
        me = _tg_request(token, "getMe")
        if not me.get("ok"):
            _fail("Telegram getMe", str(me))
            return 1
        username = me["result"].get("username", "unknown")
        _ok("Telegram getMe", f"@{username}")
    except URLError as exc:
        _fail("Telegram getMe", f"Network error: {exc}")
        return 1
    except Exception as exc:
        _fail("Telegram getMe", str(exc))
        return 1

    try:
        hook_info = _tg_request(token, "getWebhookInfo")
        if hook_info.get("ok"):
            url = hook_info["result"].get("url", "")
            pending = hook_info["result"].get("pending_update_count", 0)
            if url:
                _warn("Webhook is set", f"{url} (pending={pending})")
                _warn("Long polling warning", "Run deleteWebhook before start_polling")
            else:
                _ok("Webhook", f"Not set (pending={pending})")
        else:
            _warn("getWebhookInfo", str(hook_info))
    except Exception as exc:
        _warn("getWebhookInfo", str(exc))

    db_ok = await _check_db(database_url)
    if not db_ok:
        return 1

    print("\nHealth-check complete. If bot still does not respond, run deleteWebhook and restart bot.")
    print(f"Command: https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))