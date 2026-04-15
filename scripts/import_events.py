"""One-time importer for the local event dataset into PostgreSQL.

Usage:
    python scripts/import_events.py --database-url postgresql://user:pass@localhost:5432/conference_db

If --database-url is omitted, the script uses DATABASE_URL or the standard
POSTGRES_* fallback from shared.config.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.event_dataset import load_event_dataset, normalize_event_record


load_dotenv()


TABLE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source              TEXT,
    url                 TEXT UNIQUE,
    name                TEXT,
    description         TEXT,
    category            TEXT,
    location            TEXT,
    country             TEXT,
    event_date          DATE,
    speakers            JSONB DEFAULT '[]'::jsonb,
    exhibitors          JSONB DEFAULT '[]'::jsonb,
    ticket_price        JSONB DEFAULT '[]'::jsonb,
    expected_turnaround TEXT,
    search_tsv          TSVECTOR DEFAULT ''::tsvector,
    raw_event           JSONB NOT NULL DEFAULT '{}'::jsonb,
    domain              TEXT,
    topic               TEXT,
    geography           TEXT,
    city                TEXT,
    start_date          DATE,
    end_date            DATE,
    budget_usd          BIGINT,
    target_audience     INT,
    website             TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE events ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS url TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS location TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS country TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS event_date DATE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS speakers JSONB DEFAULT '[]'::jsonb;
ALTER TABLE events ADD COLUMN IF NOT EXISTS exhibitors JSONB DEFAULT '[]'::jsonb;
ALTER TABLE events ADD COLUMN IF NOT EXISTS ticket_price JSONB DEFAULT '[]'::jsonb;
ALTER TABLE events ADD COLUMN IF NOT EXISTS expected_turnaround TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS search_tsv TSVECTOR DEFAULT ''::tsvector;
ALTER TABLE events ADD COLUMN IF NOT EXISTS raw_event JSONB DEFAULT '{}'::jsonb;
ALTER TABLE events ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS topic TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS geography TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS start_date DATE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS end_date DATE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS budget_usd BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS target_audience INT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS website TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_events_name ON events (name);
CREATE INDEX IF NOT EXISTS idx_events_category ON events (category);
CREATE INDEX IF NOT EXISTS idx_events_country ON events (country);
CREATE INDEX IF NOT EXISTS idx_events_location ON events (location);
CREATE INDEX IF NOT EXISTS idx_events_source ON events (source);
CREATE INDEX IF NOT EXISTS idx_events_event_date ON events (event_date);
CREATE INDEX IF NOT EXISTS idx_events_search_tsv ON events USING GIN (search_tsv);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_url_unique ON events (url);
"""


INSERT_SQL = """
INSERT INTO events (
    source,
    url,
    name,
    description,
    category,
    location,
    country,
    event_date,
    speakers,
    exhibitors,
    ticket_price,
    expected_turnaround,
    search_tsv,
    raw_event,
    domain,
    topic,
    geography,
    city,
    website
) VALUES (
    :source,
    :url,
    :name,
    :description,
    :category,
    :location,
    :country,
    :event_date,
    CAST(:speakers AS jsonb),
    CAST(:exhibitors AS jsonb),
    CAST(:ticket_price AS jsonb),
    :expected_turnaround,
    to_tsvector(
        'english',
        concat_ws(
            ' ',
            coalesce(:name, ''),
            coalesce(:description, ''),
            coalesce(:category, ''),
            coalesce(:location, ''),
            coalesce(:country, ''),
            coalesce(:source, ''),
            coalesce(:url, '')
        )
    ),
    CAST(:raw_event AS jsonb),
    :domain,
    :topic,
    :geography,
    :city,
    :website
)
ON CONFLICT (url) DO UPDATE SET
    source = EXCLUDED.source,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    location = EXCLUDED.location,
    country = EXCLUDED.country,
    event_date = EXCLUDED.event_date,
    speakers = EXCLUDED.speakers,
    exhibitors = EXCLUDED.exhibitors,
    ticket_price = EXCLUDED.ticket_price,
    expected_turnaround = EXCLUDED.expected_turnaround,
    search_tsv = EXCLUDED.search_tsv,
    raw_event = EXCLUDED.raw_event,
    domain = EXCLUDED.domain,
    topic = EXCLUDED.topic,
    geography = EXCLUDED.geography,
    city = EXCLUDED.city,
    website = EXCLUDED.website,
    updated_at = NOW()
"""


def _dedupe_events(events: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for event in events:
        key = event.get("url") or f"{event.get('name')}|{event.get('date')}|{event.get('source')}"
        deduped[key] = event
    return list(deduped.values())


async def import_events(database_url: str, batch_size: int = 250) -> None:
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        for statement in TABLE_SQL.split(";"):
            sql = statement.strip()
            if sql:
                await conn.execute(text(sql))
        await conn.execute(text("TRUNCATE TABLE events"))

    events = _dedupe_events(load_event_dataset())
    rows = [normalize_event_record(event) for event in events]

    async with session_factory() as session:
        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            payload = [
                {
                    **row,
                    "speakers": json.dumps(row["speakers"]),
                    "exhibitors": json.dumps(row["exhibitors"]),
                    "ticket_price": json.dumps(row["ticket_price"]),
                    "raw_event": json.dumps(row["raw_event"]),
                }
                for row in chunk
            ]
            await session.execute(text(INSERT_SQL), payload)
            await session.commit()

    await engine.dispose()
    print(f"Imported {len(rows)} events into PostgreSQL")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import all_events_final.json into PostgreSQL")
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL connection string. Defaults to DATABASE_URL or the standard POSTGRES_* fallback.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Number of events to upsert per batch.",
    )
    args = parser.parse_args()

    if args.database_url:
        database_url = args.database_url
    else:
        from shared.config import build_default_database_url

        database_url = build_default_database_url()

    asyncio.run(import_events(database_url, batch_size=args.batch_size))


if __name__ == "__main__":
    main()