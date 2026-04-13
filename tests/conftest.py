"""
Shared fixtures and helpers for the MCP tool test suite.

Every tool in mcp_server/server.py is tested by calling the underlying
Python function directly, with external dependencies (HTTP, database,
OpenAI embeddings) replaced by deterministic mocks.  This ensures we
are validating the *tool logic* — not the network or the LLM.
"""

import asyncio
import json
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Pytest-asyncio configuration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Helpers: fake DB session, fake OpenAI client, fake httpx
# ---------------------------------------------------------------------------

class FakeRow:
    """Simulates a SQLAlchemy Row with _mapping support."""

    def __init__(self, data: dict):
        self._data = data
        self._mapping = data

    def __getitem__(self, idx):
        return list(self._data.values())[idx]

    def __iter__(self):
        return iter(self._data.values())


class FakeResult:
    """Simulates a SQLAlchemy CursorResult."""

    def __init__(self, rows: list[dict]):
        self._rows = [FakeRow(r) for r in rows]

    def fetchall(self):
        return self._rows


class FakeDBSession:
    """Async context-manager that mimics an AsyncSession."""

    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []
        self.executed = []  # track all executed queries

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return FakeResult(self._rows)

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def make_session_factory(rows: list[dict] | None = None):
    """Return a callable that produces FakeDBSession instances."""
    def factory():
        return FakeDBSession(rows)
    return factory


class FakeEmbeddingData:
    def __init__(self):
        self.embedding = [0.1] * 1536


class FakeEmbeddingResponse:
    def __init__(self):
        self.data = [FakeEmbeddingData()]


def make_fake_openai_client():
    """Return a mock AsyncAzureOpenAI whose embeddings.create returns a
    deterministic embedding vector."""
    client = AsyncMock()
    client.embeddings.create = AsyncMock(return_value=FakeEmbeddingResponse())
    return client
