import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from shared.config import build_default_database_url
import dotenv 
dotenv.load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", build_default_database_url()).replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(DATABASE_URL)
session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app):
    """Ensure the registry table exists on startup."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_registry (
                name          TEXT PRIMARY KEY,
                url           TEXT NOT NULL,
                card          JSONB NOT NULL,
                registered_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """))
    yield


app = FastAPI(title="Agent Card Registry", lifespan=lifespan)


class RegisterRequest(BaseModel):
    agent_url: str
    card: dict | None = None


@app.post("/register")
async def register_agent(req: RegisterRequest):
    """Agent calls this on startup to register its card."""
    if req.card:
        card = req.card
    else:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{req.agent_url}/.well-known/agent.json")
                r.raise_for_status()
                card = r.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=502,
                detail=f"Could not connect to agent at {req.agent_url} to fetch agent card. "
                       "Pass the card directly in the request body."
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail=f"Timed out connecting to agent at {req.agent_url}. "
                       "Pass the card directly in the request body."
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Agent at {req.agent_url} returned HTTP {e.response.status_code}."
            )

    async with session_factory() as session:
        await session.execute(text("""
            INSERT INTO agent_registry (name, url, card)
            VALUES (:name, :url, CAST(:card AS jsonb))
            ON CONFLICT (name) DO UPDATE
            SET url = EXCLUDED.url, card = EXCLUDED.card, updated_at = NOW()
        """), {
            "name": card["name"],
            "url": req.agent_url,
            "card": json.dumps(card)
        })
        await session.commit()

    return {"registered": card["name"]}


@app.get("/agents")
async def list_agents():
    """List all registered agents and their capabilities."""
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT url, card FROM agent_registry ORDER BY name")
        )
        return [{"url": r[0], "card": r[1]} for r in result.fetchall()]


@app.get("/agents/{agent_name}")
async def get_agent(agent_name: str):
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT url, card FROM agent_registry WHERE name = :name"),
            {"name": agent_name}
        )
        row = result.fetchone()
    if not row:
        raise HTTPException(404, f"Agent '{agent_name}' not found")
    return {"url": row[0], "card": row[1]}


@app.get("/discover")
async def discover(capability: str = None, domain: str = None):
    """Find agents by capability or domain — used by orchestrator at runtime."""
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT url, card FROM agent_registry ORDER BY name")
        )
        rows = result.fetchall()

    results = []
    for url, card in rows:
        if capability:
            caps = [c["name"] for c in card.get("capabilities", [])]
            if capability not in caps:
                continue
        if domain and domain not in card.get("domains", []):
            continue
        results.append({"url": url, "card": card})
    return results


@app.get("/health")
async def health():
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM agent_registry")
        )
        count = result.scalar()
    return {"status": "ok", "registered_agents": count}
