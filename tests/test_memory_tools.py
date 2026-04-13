"""
Unit tests for memory-related MCP tools:
  vector_search, write_memory, query_past_experiences, query_guidelines_and_rules
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeDBSession, FakeResult, FakeRow, make_fake_openai_client


# ---------------------------------------------------------------------------
# vector_search
# ---------------------------------------------------------------------------

class TestVectorSearch:
    """Verify semantic search queries the DB with the right embedding."""

    @pytest.mark.asyncio
    async def test_returns_scored_results(self):
        fake_rows = [
            {"content": "Great venue in Mumbai", "metadata": {"city": "Mumbai"}, "score": 0.95},
            {"content": "Budget tips for India", "metadata": {"region": "India"}, "score": 0.82},
        ]
        # FakeRow needs to support positional indexing for the SELECT columns
        fake_result_rows = []
        for r in fake_rows:
            row = MagicMock()
            row.__getitem__ = lambda self, idx, data=r: list(data.values())[idx]
            fake_result_rows.append(row)

        fake_session = AsyncMock()
        fake_result = MagicMock()
        fake_result.fetchall.return_value = fake_result_rows
        fake_session.execute = AsyncMock(return_value=fake_result)
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        fake_openai = make_fake_openai_client()

        with patch("mcp_server.server.session_factory", return_value=fake_session), \
             patch("mcp_server.server.openai_client", fake_openai):
            from mcp_server.server import vector_search
            results = await vector_search("venue in Mumbai", namespace="venue_agent", limit=2)

        assert len(results) == 2
        assert results[0]["content"] == "Great venue in Mumbai"
        assert results[0]["score"] == 0.95
        # Verify embeddings were created
        fake_openai.embeddings.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# write_memory
# ---------------------------------------------------------------------------

class TestWriteMemory:
    """Verify that write_memory stores content with an embedding."""

    @pytest.mark.asyncio
    async def test_writes_and_commits(self):
        fake_session = AsyncMock()
        fake_session.execute = AsyncMock()
        fake_session.commit = AsyncMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        fake_openai = make_fake_openai_client()

        with patch("mcp_server.server.session_factory", return_value=fake_session), \
             patch("mcp_server.server.openai_client", fake_openai):
            from mcp_server.server import write_memory
            result = await write_memory(
                namespace="venue_agent",
                content="Discovered that Hotel XYZ has bad WiFi",
                metadata={"city": "Bangalore", "category": "wifi_issue"},
            )

        assert result is True
        fake_session.execute.assert_awaited_once()
        fake_session.commit.assert_awaited_once()
        fake_openai.embeddings.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# query_past_experiences — vector path
# ---------------------------------------------------------------------------

class TestQueryPastExperiencesVector:
    """Verify vector-similarity path when query is provided."""

    @pytest.mark.asyncio
    async def test_vector_search_path(self):
        fake_rows = []
        row = MagicMock()
        data = {"content": "WiFi crashed at 2024 Delhi event", "metadata": {"city": "Delhi"}, "relevance_score": 0.91}
        row.__getitem__ = lambda self, idx, d=data: list(d.values())[idx]
        fake_rows.append(row)

        fake_session = AsyncMock()
        fake_result = MagicMock()
        fake_result.fetchall.return_value = fake_rows
        fake_session.execute = AsyncMock(return_value=fake_result)
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        fake_openai = make_fake_openai_client()

        with patch("mcp_server.server.session_factory", return_value=fake_session), \
             patch("mcp_server.server.openai_client", fake_openai):
            from mcp_server.server import query_past_experiences
            results = await query_past_experiences(query="WiFi issues at events")

        assert len(results) == 1
        assert "WiFi crashed" in results[0]["content"]
        fake_openai.embeddings.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# query_past_experiences — filter path
# ---------------------------------------------------------------------------

class TestQueryPastExperiencesFilter:
    """Verify metadata-filter path when no query is provided."""

    @pytest.mark.asyncio
    async def test_filter_by_city(self):
        fake_rows = []
        row = MagicMock()
        data = {"content": "London venue was excellent", "metadata": {"city": "London"}}
        row.__getitem__ = lambda self, idx, d=data: list(d.values())[idx]
        fake_rows.append(row)

        fake_session = AsyncMock()
        fake_result = MagicMock()
        fake_result.fetchall.return_value = fake_rows
        fake_session.execute = AsyncMock(return_value=fake_result)
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_past_experiences
            results = await query_past_experiences(city="London")

        assert len(results) == 1
        assert results[0]["content"] == "London venue was excellent"


# ---------------------------------------------------------------------------
# query_guidelines_and_rules
# ---------------------------------------------------------------------------

class TestQueryGuidelinesAndRules:
    """Verify procedural-memory rule queries."""

    @pytest.mark.asyncio
    async def test_returns_rules_ordered_by_severity(self):
        fake_rows = []
        for data in [
            {"topic": "gdpr", "region": "europe", "domain": None,
             "rule": "Must obtain consent", "severity": "critical", "source": "EU regulation"},
            {"topic": "budget", "region": "global", "domain": None,
             "rule": "Venue <= 30% of budget", "severity": "warning", "source": "SOP"},
        ]:
            row = MagicMock()
            row.__getitem__ = lambda self, idx, d=data: list(d.values())[idx]
            fake_rows.append(row)

        fake_session = AsyncMock()
        fake_result = MagicMock()
        fake_result.fetchall.return_value = fake_rows
        fake_session.execute = AsyncMock(return_value=fake_result)
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_guidelines_and_rules
            results = await query_guidelines_and_rules(region="europe")

        assert len(results) == 2
        assert results[0]["rule"] == "Must obtain consent"
        assert results[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_no_filters_returns_all(self):
        """When no filters are given, query returns all rules."""
        fake_rows = []
        data = {"topic": "general", "region": "global", "domain": None,
                "rule": "Always have backup plan", "severity": "info", "source": "best practice"}
        row = MagicMock()
        row.__getitem__ = lambda self, idx, d=data: list(d.values())[idx]
        fake_rows.append(row)

        fake_session = AsyncMock()
        fake_result = MagicMock()
        fake_result.fetchall.return_value = fake_rows
        fake_session.execute = AsyncMock(return_value=fake_result)
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_guidelines_and_rules
            results = await query_guidelines_and_rules()

        assert len(results) == 1
        # Verify query contains WHERE TRUE (no filters)
        executed_sql = str(fake_session.execute.call_args[0][0])
        assert "TRUE" in executed_sql
