"""
Orchestration Checkpoints — crash-resilient state management for EventOps.

Saves the full orchestration state to PostgreSQL after each significant step,
enabling resume-from-checkpoint on crash/restart. The checkpoint lifecycle:

1. _orchestrate() starts → checkpoint created with status='planning'
2. Task plan built → checkpoint updated with task_plan
3. Each agent completes → checkpoint updated with that agent's output
4. Conflict resolution → checkpoint updated with conflicts
5. Final plan assembled → status='completed'

On crash, EventOps checks for incomplete checkpoints on startup and resumes
from the last saved state, skipping agents that already completed.
"""

import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from shared.config import config


class CheckpointStore:
    """Manages orchestration checkpoints in PostgreSQL."""

    def __init__(self, db_url: str = None):
        url = db_url or config.database_url
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://")
        )
        self.session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create(self, session_id: str, event_input: dict) -> None:
        """Create a new checkpoint when orchestration starts."""
        async with self.session_factory() as session:
            await session.execute(text("""
                INSERT INTO orchestration_checkpoints
                    (session_id, event_input, status)
                VALUES (:sid, CAST(:input AS jsonb), 'planning')
                ON CONFLICT (session_id) DO UPDATE
                SET event_input = EXCLUDED.event_input,
                    status = 'planning',
                    task_plan = NULL,
                    completed_agents = CAST('[]' AS jsonb),
                    agent_outputs = CAST('{}' AS jsonb),
                    conflicts = CAST('[]' AS jsonb),
                    final_plan = NULL,
                    current_agent = NULL,
                    error_message = NULL,
                    updated_at = NOW()
            """), {
                "sid": session_id,
                "input": json.dumps(event_input)
            })
            await session.commit()

    async def save_plan(self, session_id: str, task_plan: list[dict]) -> None:
        """Save the LLM-generated task plan."""
        async with self.session_factory() as session:
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET task_plan = CAST(:plan AS jsonb),
                    status = 'executing',
                    updated_at = NOW()
                WHERE session_id = :sid
            """), {
                "sid": session_id,
                "plan": json.dumps(task_plan)
            })
            await session.commit()

    async def save_agent_output(self, session_id: str, agent_name: str,
                                 output: dict) -> None:
        """Save an individual agent's output after it completes."""
        async with self.session_factory() as session:
            # Atomic update: add to completed_agents list and agent_outputs dict
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET agent_outputs = agent_outputs || CAST(:output AS jsonb),
                    completed_agents = (
                        SELECT jsonb_agg(DISTINCT val)
                        FROM (
                            SELECT jsonb_array_elements(completed_agents) AS val
                            UNION
                            SELECT CAST(:agent_name AS jsonb)
                        ) sub
                    ),
                    current_agent = NULL,
                    updated_at = NOW()
                WHERE session_id = :sid
            """), {
                "sid": session_id,
                "output": json.dumps({agent_name: output}),
                "agent_name": json.dumps(agent_name)
            })
            await session.commit()

    async def save_current_agent(self, session_id: str, agent_name: str) -> None:
        """Mark which agent is currently running (for resume tracking)."""
        async with self.session_factory() as session:
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET current_agent = :agent, status = 'executing', updated_at = NOW()
                WHERE session_id = :sid
            """), {"sid": session_id, "agent": agent_name})
            await session.commit()

    async def save_conflicts(self, session_id: str, resolved: dict) -> None:
        """Save conflict resolution results."""
        async with self.session_factory() as session:
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET conflicts = CAST(:conflicts AS jsonb),
                    final_plan = CAST(:plan AS jsonb),
                    status = 'completed',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE session_id = :sid
            """), {
                "sid": session_id,
                "conflicts": json.dumps(resolved.get("conflicts_detected", [])),
                "plan": json.dumps(resolved)
            })
            await session.commit()

    async def mark_failed(self, session_id: str, error: str) -> None:
        """Mark an orchestration as failed."""
        async with self.session_factory() as session:
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET status = 'failed', error_message = :error, updated_at = NOW()
                WHERE session_id = :sid
            """), {"sid": session_id, "error": error})
            await session.commit()

    async def mark_canceled(self, session_id: str, reason: str) -> None:
        """Mark an orchestration as canceled by the user."""
        async with self.session_factory() as session:
            await session.execute(text("""
                UPDATE orchestration_checkpoints
                SET status = 'canceled', error_message = :reason, updated_at = NOW()
                WHERE session_id = :sid
            """), {"sid": session_id, "reason": reason})
            await session.commit()

    async def load(self, session_id: str) -> dict | None:
        """Load a checkpoint by session ID. Returns None if not found."""
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT session_id, event_input, task_plan, completed_agents,
                       agent_outputs, conflicts, final_plan, status,
                       current_agent, error_message, started_at, updated_at
                FROM orchestration_checkpoints
                WHERE session_id = :sid
            """), {"sid": session_id})
            row = result.fetchone()
            if not row:
                return None
            return {
                "session_id": row[0],
                "event_input": row[1],
                "task_plan": row[2],
                "completed_agents": row[3] or [],
                "agent_outputs": row[4] or {},
                "conflicts": row[5] or [],
                "final_plan": row[6],
                "status": row[7],
                "current_agent": row[8],
                "error_message": row[9],
                "started_at": row[10].isoformat() if row[10] else None,
                "updated_at": row[11].isoformat() if row[11] else None,
            }

    async def find_incomplete(self) -> list[dict]:
        """Find all checkpoints that didn't complete (for crash recovery)."""
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT session_id, event_input, task_plan, completed_agents,
                       agent_outputs, status, current_agent, started_at
                FROM orchestration_checkpoints
                  WHERE status NOT IN ('completed', 'failed', 'canceled')
                ORDER BY started_at DESC
            """))
            rows = result.fetchall()
            return [
                {
                    "session_id": r[0],
                    "event_input": r[1],
                    "task_plan": r[2],
                    "completed_agents": r[3] or [],
                    "agent_outputs": r[4] or {},
                    "status": r[5],
                    "current_agent": r[6],
                    "started_at": r[7].isoformat() if r[7] else None,
                }
                for r in rows
            ]

    async def delete(self, session_id: str) -> None:
        """Delete a checkpoint (cleanup after completed sessions)."""
        async with self.session_factory() as session:
            await session.execute(
                text("DELETE FROM orchestration_checkpoints WHERE session_id = :sid"),
                {"sid": session_id}
            )
            await session.commit()
