"""
Unit tests for shared-state and agent-communication MCP tools:
  read_working_memory, write_working_memory, discover_agents, ask_agent
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_fake_db_session(rows=None):
    rows = rows or []
    fake_result_rows = []
    for r in rows:
        row = MagicMock()
        row.__getitem__ = lambda self, idx, d=r: list(d.values())[idx]
        fake_result_rows.append(row)

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.fetchall.return_value = fake_result_rows
    fake_session.execute = AsyncMock(return_value=fake_result)
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    return fake_session


# ---------------------------------------------------------------------------
# read_working_memory
# ---------------------------------------------------------------------------

class TestReadWorkingMemory:
    """Verify working-memory reads with different filter combos."""

    @pytest.mark.asyncio
    async def test_read_all_for_session(self):
        now = datetime(2026, 4, 12, tzinfo=timezone.utc)
        rows = [
            {"agent": "venue_agent", "key": "shortlist", "value": '["Grand Hall"]', "updated_at": now},
            {"agent": "pricing_agent", "key": "pricing", "value": '{"early_bird": 100}', "updated_at": now},
        ]
        fake_session = _make_fake_db_session(rows)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import read_working_memory
            results = await read_working_memory(session_id="test-session-1")

        assert len(results) == 2
        assert results[0]["agent"] == "venue_agent"
        assert results[1]["key"] == "pricing"

    @pytest.mark.asyncio
    async def test_read_specific_agent_key(self):
        now = datetime(2026, 4, 12, tzinfo=timezone.utc)
        rows = [{"agent": "venue_agent", "key": "shortlist", "value": '["Grand Hall"]', "updated_at": now}]
        fake_session = _make_fake_db_session(rows)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import read_working_memory
            results = await read_working_memory(
                session_id="sess-1", agent_name="venue_agent", key="shortlist"
            )

        assert len(results) == 1
        assert results[0]["key"] == "shortlist"

        # Verify SQL included both agent_name and key filters
        executed_sql = str(fake_session.execute.call_args[0][0])
        assert "agent_name" in executed_sql
        assert "key" in executed_sql


# ---------------------------------------------------------------------------
# write_working_memory
# ---------------------------------------------------------------------------

class TestWriteWorkingMemory:
    """Verify working-memory writes with upsert semantics."""

    @pytest.mark.asyncio
    async def test_writes_and_commits(self):
        fake_session = _make_fake_db_session()

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import write_working_memory
            result = await write_working_memory(
                session_id="sess-1",
                agent_name="venue_agent",
                key="shortlist",
                value='["Grand Hall", "Tech Park"]',
            )

        assert result is True
        fake_session.execute.assert_awaited_once()
        fake_session.commit.assert_awaited_once()

        # Verify the INSERT ... ON CONFLICT upsert pattern
        executed_sql = str(fake_session.execute.call_args[0][0])
        assert "INSERT INTO working_memory" in executed_sql
        assert "ON CONFLICT" in executed_sql


# ---------------------------------------------------------------------------
# discover_agents
# ---------------------------------------------------------------------------

class TestDiscoverAgents:
    """Verify agent discovery from the registry."""

    @pytest.mark.asyncio
    async def test_discovers_agents(self):
        fake_registry_response = [
            {
                "card": {
                    "name": "venue_agent",
                    "description": "Finds venues",
                    "capabilities": [
                        {"name": "venue_search", "description": "Search for venues"}
                    ],
                    "domains": ["conference"],
                }
            },
            {
                "card": {
                    "name": "pricing_agent",
                    "description": "Calculates pricing",
                    "capabilities": [
                        {"name": "pricing", "description": "Price tickets"}
                    ],
                    "domains": ["conference"],
                }
            },
        ]

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = fake_registry_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import discover_agents
            results = await discover_agents()

        assert len(results) == 2
        assert results[0]["name"] == "venue_agent"
        assert results[1]["name"] == "pricing_agent"
        assert "venue_search" in results[0]["capabilities"][0]

    @pytest.mark.asyncio
    async def test_discover_with_capability_filter(self):
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import discover_agents
            results = await discover_agents(capability="venue_search")

        # Verify capability param was passed
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["capability"] == "venue_search"


# ---------------------------------------------------------------------------
# ask_agent
# ---------------------------------------------------------------------------

class TestAskAgent:
    """Verify agent-to-agent communication via the registry and A2A protocol."""

    @pytest.mark.asyncio
    async def test_sends_task_and_gets_response(self):
        # Step 1: Registry lookup returns agent URL
        registry_response = MagicMock()
        registry_response.raise_for_status = MagicMock()
        registry_response.json.return_value = {"url": "http://venue-agent:8001"}

        # Step 2: POST /tasks creates a task
        task_create_response = MagicMock()
        task_create_response.raise_for_status = MagicMock()
        task_create_response.json.return_value = {"task_id": "task-123"}

        # Step 3: GET /tasks/{id}/events streams SSE
        final_event = 'data: {"final": true}'

        # Step 4: GET /tasks/{id} returns final result
        task_result_response = MagicMock()
        task_result_response.json.return_value = {
            "artifacts": [
                {
                    "parts": [
                        {"type": "text", "text": "Top venue: Grand Hall in Bangalore"}
                    ]
                }
            ]
        }

        # Build a mock streaming response
        class FakeStreamResponse:
            async def aiter_lines(self):
                yield final_event

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "/agents/" in url:
                return registry_response
            elif "/tasks/task-123" in url and "/events" not in url:
                return task_result_response
            return MagicMock()

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = AsyncMock(return_value=task_create_response)
        mock_client.stream = MagicMock(return_value=FakeStreamResponse())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import ask_agent
            result = await ask_agent(
                agent_name="venue_agent",
                question="Find top venues in Bangalore for 1000 attendees",
                session_id="sess-1",
            )

        assert "Grand Hall" in result
        assert "Bangalore" in result

    @pytest.mark.asyncio
    async def test_agent_not_found_returns_error(self):
        registry_response = MagicMock()
        registry_response.raise_for_status = MagicMock()
        registry_response.json.return_value = {"url": None}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=registry_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import ask_agent
            result = await ask_agent(
                agent_name="nonexistent_agent",
                question="Hello?",
                session_id="sess-1",
            )

        parsed = json.loads(result)
        assert "error" in parsed
        assert "not found" in parsed["error"]
