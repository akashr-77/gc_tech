import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

class ProceduralMemory:
    """Structured Postgres queries for facts that don't need semantic search."""

    def __init__(self, db_url: str):
        engine = create_async_engine(db_url.replace("postgresql://", "postgresql+asyncpg://"))
        self.session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def get_venues(self, city: str, max_price: int = None, min_capacity: int = None) -> list[dict]:
        filters = ["LOWER(city) = LOWER(:city)"]
        params = {"city": city}
        if max_price:
            filters.append("price_per_day <= :max_price")
            params["max_price"] = max_price
        if min_capacity:
            filters.append("capacity_max >= :min_capacity")
            params["min_capacity"] = min_capacity
        where = " AND ".join(filters)
        async with self.session_factory() as session:
            result = await session.execute(
                text(f"SELECT * FROM venues WHERE {where} ORDER BY price_per_day"),
                params
            )
            return [dict(r._mapping) for r in result.fetchall()]

    async def get_sponsors_by_industry(self, industry: str, geography: str = None) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT s.*, COUNT(sh.id) as event_count,
                       MAX(sh.event_date) as last_sponsored
                FROM sponsors s
                LEFT JOIN sponsor_history sh ON sh.sponsor_id = s.id
                WHERE LOWER(s.industry) LIKE LOWER(:industry)
                GROUP BY s.id
                ORDER BY event_count DESC
            """), {"industry": f"%{industry}%"})
            return [dict(r._mapping) for r in result.fetchall()]

    async def get_speakers_by_topic(self, topic: str) -> list[dict]:
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT * FROM speakers
                WHERE :topic = ANY(topics)
                   OR bio ILIKE :topic_like
                ORDER BY follower_count DESC NULLS LAST
                LIMIT 20
            """), {"topic": topic, "topic_like": f"%{topic}%"})
            return [dict(r._mapping) for r in result.fetchall()]

    async def get_pricing_model(self, domain: str, geography: str, audience: int) -> dict:
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT * FROM pricing_models
                WHERE event_domain = :domain
                  AND (geography = :geo OR geography = 'global')
                ORDER BY ABS(audience_size - :audience) ASC
                LIMIT 1
            """), {"domain": domain, "geo": geography, "audience": audience})
            row = result.fetchone()
            return dict(row._mapping) if row else {}

    async def get_communities_by_niche(self, niche: str, platform: str = None) -> list[dict]:
        filters = ["niche ILIKE :niche"]
        params = {"niche": f"%{niche}%"}
        if platform:
            filters.append("platform = :platform")
            params["platform"] = platform
        where = " AND ".join(filters)
        async with self.session_factory() as session:
            result = await session.execute(
                text(f"SELECT * FROM communities WHERE {where} ORDER BY member_count DESC"),
                params
            )
            return [dict(r._mapping) for r in result.fetchall()]

    async def save_task_result(self, task_id: str, session_id: str,
                               agent_name: str, status: str,
                               output: dict, confidence: float):
        async with self.session_factory() as session:
            await session.execute(text("""
                INSERT INTO agent_tasks
                  (id, session_id, agent_name, status, output_data, confidence, completed_at)
                VALUES (:id, :sid, :agent, :status, CAST(:output AS jsonb), :conf, NOW())
                ON CONFLICT (id) DO UPDATE
                  SET status=EXCLUDED.status, output_data=EXCLUDED.output_data,
                      confidence=EXCLUDED.confidence, updated_at=NOW(), completed_at=NOW()
            """), {
                "id": task_id, "sid": session_id, "agent": agent_name,
                "status": status, "output": json.dumps(output), "conf": confidence
            })
            await session.commit()