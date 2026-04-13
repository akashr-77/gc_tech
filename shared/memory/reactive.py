"""
Reactive Monitor — event queue and monitoring state for EventOps.

Manages the reactive_events table and monitor state on checkpoints.
The reactive loop uses this to:
1. Check for pending events (user requests, triggers, data changes)
2. Mark events as processed
3. Track monitoring state (active/inactive, cycle count)
"""

import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from shared.config import config


class ReactiveMonitor:
    """Manages the reactive event queue and monitoring lifecycle."""

    def __init__(self, db_url: str = None):
        url = db_url or config.database_url
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://")
        )
        self.session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # ─── Event Queue ─────────────────────────────────────────────────────────

    async def push_event(self, session_id: str, event_type: str,
                         source: str = None, payload: dict = None) -> str:
        """Push a new event into the queue. Returns the event ID."""
        async with self.session_factory() as session:
            result = await session.execute(text("""
                INSERT INTO reactive_events (session_id, event_type, source, payload)
                VALUES (:sid, :type, :source, CAST(:payload AS jsonb))
                RETURNING id
            """), {
                "sid": session_id,
                "type": event_type,
                "source": source or "system",
                "payload": json.dumps(payload or {})
            })
            await session.commit()
            row = result.fetchone()
            return str(row[0])

    async def poll_events(self, session_id: str) -> list[dict]:
        """Fetch all unprocessed events for a session, oldest first."""
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT id, event_type, source, payload, created_at
                FROM reactive_events
                WHERE session_id = :sid AND processed = FALSE
                ORDER BY created_at ASC
            """), {"sid": session_id})
            rows = result.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "event_type": r[1],
                    "source": r[2],
                    "payload": r[3],
                    "created_at": r[4].isoformat() if r[4] else None
                }
                for r in rows
            ]

    async def mark_processed(self, event_ids: list[str]) -> None:
        """Mark events as processed after the monitor handles them."""
        if not event_ids:
            return
        async with self.session_factory() as session:
            # Use ANY() for batch update
            await session.execute(text("""
                UPDATE reactive_events
                SET processed = TRUE
                WHERE id = ANY(CAST(:ids AS uuid[]))
            """), {"ids": event_ids})
            await session.commit()

    # ─── Monitor State ───────────────────────────────────────────────────────

    async def activate_monitor(self, session_id: str) -> None:
        """Mark a session's checkpoint as actively monitored."""
        async with self.session_factory() as session:
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET monitor_active = TRUE, status = 'monitoring', updated_at = NOW()
                WHERE session_id = :sid
            """), {"sid": session_id})
            await session.commit()

    async def deactivate_monitor(self, session_id: str) -> None:
        """Stop monitoring a session."""
        async with self.session_factory() as session:
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET monitor_active = FALSE, updated_at = NOW()
                WHERE session_id = :sid
            """), {"sid": session_id})
            await session.commit()

    async def increment_cycle(self, session_id: str) -> int:
        """Increment and return the monitoring cycle counter."""
        async with self.session_factory() as session:
            result = await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET monitor_cycle = monitor_cycle + 1, updated_at = NOW()
                WHERE session_id = :sid
                RETURNING monitor_cycle
            """), {"sid": session_id})
            await session.commit()
            row = result.fetchone()
            return row[0] if row else 0

    async def get_monitored_sessions(self) -> list[str]:
        """Get all session IDs that are actively being monitored."""
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT session_id FROM orchestration_checkpoints
                WHERE monitor_active = TRUE
            """))
            return [str(r[0]) for r in result.fetchall()]

    async def cleanup_old_events(self, session_id: str) -> int:
        """Delete processed events older than 1 hour."""
        async with self.session_factory() as session:
            result = await session.execute(text("""
                DELETE FROM reactive_events
                WHERE session_id = :sid
                  AND processed = TRUE
                  AND created_at < NOW() - INTERVAL '1 hour'
            """), {"sid": session_id})
            await session.commit()
            return result.rowcount
