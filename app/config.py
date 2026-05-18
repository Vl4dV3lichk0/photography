from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv


load_dotenv()


def _parse_admin_ids(raw: str) -> List[int]:
    ids: List[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        ids.append(int(chunk))
    return ids


@dataclass(slots=True)
class Settings:
    bot_token: str
    owner_tg_id: int
    admin_ids: List[int]
    database_url: str
    timezone: str
    policy_version: str


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    owner = int(os.getenv("OWNER_TG_ID", "0"))
    if owner <= 0:
        raise RuntimeError("OWNER_TG_ID must be a positive integer")

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    if owner not in admin_ids:
        admin_ids.insert(0, owner)

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    return Settings(
        bot_token=token,
        owner_tg_id=owner,
        admin_ids=admin_ids,
        database_url=database_url,
        timezone=os.getenv("TIMEZONE", "Europe/Moscow"),
        policy_version=os.getenv("POLICY_VERSION", "v1"),
    )