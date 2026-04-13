"""
Working Memory — session-scoped context store for agent collaboration.

Unlike episodic memory (vector search over past experiences) or procedural memory
(structured SQL queries), working memory is:
- Session-scoped: context lives only for the duration of a planning session
- Key/value: agents write named context slots (e.g., 'budget_envelope', 'venue_shortlist')
- Shared: any agent in the same session can read any other agent's context
- Persistent: stored in PostgreSQL, survives agent restarts within a session

This enables multi-turn workflows where:
1. pricing_agent writes its budget model → sponsor_agent reads it
2. venue_agent writes its shortlist → exhibitor_agent reads capacity data
3. eventops reads all context to make informed conflict resolution decisions
"""

import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from shared.config import config


class WorkingMemory:
    """Session-scoped key/value context store backed by PostgreSQL."""

    def __init__(self, db_url: str = None):
        url = db_url or config.database_url
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://")
        )
        self.session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def put(self, session_id: str, agent_name: str,
                  key: str, value: dict | list | str) -> None:
        """
        Write a context value for this agent in this session.
        Upserts — overwrites if the same key already exists.
        """
        val_json = json.dumps(value) if not isinstance(value, str) else json.dumps(value)
        async with self.session_factory() as session:
            await session.execute(text("""
                INSERT INTO working_memory (session_id, agent_name, key, value)
                VALUES (:sid, :agent, :key, CAST(:value AS jsonb))
                ON CONFLICT (session_id, agent_name, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """), {
                "sid": session_id, "agent": agent_name,
                "key": key, "value": val_json
            })
            await session.commit()

    async def get(self, session_id: str, agent_name: str = None,
                  key: str = None) -> dict | list[dict]:
        """
        Read context from working memory.

        - get(session_id) → all context for this session (all agents, all keys)
        - get(session_id, agent_name) → all context for one agent in this session
        - get(session_id, agent_name, key) → one specific value
        """
        filters = ["session_id = :sid"]
        params = {"sid": session_id}

        if agent_name:
            filters.append("agent_name = :agent")
            params["agent"] = agent_name
        if key:
            filters.append("key = :key")
            params["key"] = key

        where = " AND ".join(filters)

        async with self.session_factory() as session:
            result = await session.execute(
                text(f"""
                    SELECT agent_name, key, value, updated_at
                    FROM working_memory
                    WHERE {where}
                    ORDER BY updated_at DESC
                """),
                params
            )
            rows = result.fetchall()

            if key and agent_name:
                # Specific key lookup — return just the value
                return rows[0][2] if rows else None

            # Return list of context entries
            return [
                {
                    "agent": r[0],
                    "key": r[1],
                    "value": r[2],
                    "updated_at": r[3].isoformat() if r[3] else None
                }
                for r in rows
            ]

    async def get_session_summary(self, session_id: str) -> str:
        """
        Get a human-readable summary of all context in a session.
        Useful for injecting into LLM prompts as background context.
        """
        entries = await self.get(session_id)
        if not entries:
            return ""

        lines = ["## Session Context (from other agents)"]
        for entry in entries:
            val_str = json.dumps(entry["value"], indent=2) if isinstance(entry["value"], (dict, list)) else str(entry["value"])
            # Truncate long values
            if len(val_str) > 500:
                val_str = val_str[:500] + "..."
            lines.append(f"\n### {entry['agent']} → {entry['key']}\n{val_str}")

        return "\n".join(lines)

    async def clear_session(self, session_id: str) -> int:
        """Delete all working memory for a completed session. Returns count deleted."""
        async with self.session_factory() as session:
            result = await session.execute(
                text("DELETE FROM working_memory WHERE session_id = :sid"),
                {"sid": session_id}
            )
            await session.commit()
            return result.rowcount
