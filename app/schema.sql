CREATE TABLE IF NOT EXISTS admins (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT UNIQUE NOT NULL,
    added_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cities (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS working_windows (
    id BIGSERIAL PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    work_date DATE NOT NULL,
    start_hour SMALLINT NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    end_hour SMALLINT NOT NULL CHECK (end_hour BETWEEN 1 AND 24),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(city_id, work_date)
);

CREATE TABLE IF NOT EXISTS time_blocks (
    id BIGSERIAL PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    block_date DATE NOT NULL,
    start_hour SMALLINT NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    end_hour SMALLINT NOT NULL CHECK (end_hour BETWEEN 1 AND 24),
    reason TEXT NOT NULL,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    CREATE TYPE booking_status AS ENUM ('pending', 'confirmed', 'canceled', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'archived';

CREATE TABLE IF NOT EXISTS bookings (
    id BIGSERIAL PRIMARY KEY,
    user_tg_id BIGINT NOT NULL,
    username TEXT,
    city_id BIGINT NOT NULL REFERENCES cities(id),
    booking_date DATE NOT NULL,
    status booking_status NOT NULL DEFAULT 'pending',
    tg_contact TEXT NOT NULL,
    client_name TEXT,
    phone TEXT,
    shoot_type TEXT,
    comment TEXT,
    policy_version TEXT NOT NULL,
    consent_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    hour_price INTEGER NOT NULL DEFAULT 0,
    total_price INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'RUB',
    confirmed_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS booking_slots (
    id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    city_id BIGINT NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    slot_date DATE NOT NULL,
    hour SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    UNIQUE(city_id, slot_date, hour),
    UNIQUE(booking_id, hour)
);

CREATE TABLE IF NOT EXISTS booking_events_audit (
    id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT REFERENCES bookings(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    actor_tg_id BIGINT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS consents (
    id BIGSERIAL PRIMARY KEY,
    user_tg_id BIGINT NOT NULL,
    policy_version TEXT NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_log (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    ref_id BIGINT,
    sent_to BIGINT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(kind, ref_id, sent_to)
);

CREATE TABLE IF NOT EXISTS booking_archive_snapshots (
    id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT UNIQUE NOT NULL,
    snapshot JSONB NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_by BIGINT
);

CREATE TABLE IF NOT EXISTS pricing_settings (
    id INTEGER PRIMARY KEY,
    hourly_price INTEGER NOT NULL CHECK (hourly_price >= 0),
    currency TEXT NOT NULL DEFAULT 'RUB',
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO pricing_settings (id, hourly_price, currency)
VALUES (1, 5000, 'RUB')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS hour_price INTEGER NOT NULL DEFAULT 0;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS total_price INTEGER NOT NULL DEFAULT 0;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'RUB';