"""
Unit tests for structured-database MCP tools:
  query_venues, query_sponsors, query_speakers, query_communities, get_pricing_benchmark
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_fake_db_session(rows):
    """Create a mock async session that returns the given rows."""
    fake_result_rows = []
    for r in rows:
        row = MagicMock()
        row._mapping = r
        fake_result_rows.append(row)

    fake_session = AsyncMock()
    fake_result = MagicMock()
    fake_result.fetchall.return_value = fake_result_rows
    fake_session.execute = AsyncMock(return_value=fake_result)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    return fake_session


# ---------------------------------------------------------------------------
# query_venues
# ---------------------------------------------------------------------------

class TestQueryVenues:
    """Verify venue queries filter by city, price, capacity."""

    @pytest.mark.asyncio
    async def test_basic_city_query(self):
        venues = [
            {"id": 1, "name": "Grand Hall", "city": "Bangalore", "capacity_max": 2000, "price_per_day": 5000},
            {"id": 2, "name": "Tech Park", "city": "Bangalore", "capacity_max": 500, "price_per_day": 2000},
        ]
        fake_session = _make_fake_db_session(venues)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_venues
            results = await query_venues(city="Bangalore")

        assert len(results) == 2
        assert results[0]["name"] == "Grand Hall"

    @pytest.mark.asyncio
    async def test_with_price_and_capacity_filters(self):
        venues = [
            {"id": 1, "name": "Budget Venue", "city": "Delhi", "capacity_max": 1000, "price_per_day": 3000},
        ]
        fake_session = _make_fake_db_session(venues)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_venues
            results = await query_venues(city="Delhi", max_price_per_day=5000, min_capacity=500)

        assert len(results) == 1
        # Verify the SQL included price and capacity filters
        executed_sql = str(fake_session.execute.call_args[0][0])
        assert "price_per_day" in executed_sql
        assert "capacity_max" in executed_sql

    @pytest.mark.asyncio
    async def test_no_venues_found(self):
        fake_session = _make_fake_db_session([])

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_venues
            results = await query_venues(city="Antarctica")

        assert results == []


# ---------------------------------------------------------------------------
# query_sponsors
# ---------------------------------------------------------------------------

class TestQuerySponsors:
    """Verify sponsor queries with optional industry filter."""

    @pytest.mark.asyncio
    async def test_returns_sponsors_with_history(self):
        sponsors = [
            {
                "id": 1, "name": "TechCorp", "industry": "Technology",
                "event_count": 5, "last_sponsored": "2025-06-01",
                "domains_sponsored": ["conference", "hackathon"],
            },
        ]
        fake_session = _make_fake_db_session(sponsors)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_sponsors
            results = await query_sponsors(industry="Technology")

        assert len(results) == 1
        assert results[0]["name"] == "TechCorp"
        assert results[0]["event_count"] == 5


# ---------------------------------------------------------------------------
# query_speakers
# ---------------------------------------------------------------------------

class TestQuerySpeakers:
    """Verify speaker queries by topic."""

    @pytest.mark.asyncio
    async def test_finds_speakers_by_topic(self):
        speakers = [
            {"id": 1, "name": "Dr. AI Expert", "topics": ["AI", "ML"],
             "bio": "Leading AI researcher", "follower_count": 50000},
        ]
        fake_session = _make_fake_db_session(speakers)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_speakers
            results = await query_speakers(topic="AI")

        assert len(results) == 1
        assert results[0]["name"] == "Dr. AI Expert"


# ---------------------------------------------------------------------------
# query_communities
# ---------------------------------------------------------------------------

class TestQueryCommunities:
    """Verify community queries by niche and platform."""

    @pytest.mark.asyncio
    async def test_finds_communities(self):
        communities = [
            {"id": 1, "name": "AI India", "niche": "Artificial Intelligence",
             "platform": "meetup", "member_count": 15000},
        ]
        fake_session = _make_fake_db_session(communities)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_communities
            results = await query_communities(niche="AI", platform="meetup")

        assert len(results) == 1
        assert results[0]["name"] == "AI India"
        assert results[0]["member_count"] == 15000

    @pytest.mark.asyncio
    async def test_without_platform_filter(self):
        communities = [
            {"id": 1, "name": "ML Global", "niche": "Machine Learning",
             "platform": "discord", "member_count": 8000},
        ]
        fake_session = _make_fake_db_session(communities)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import query_communities
            results = await query_communities(niche="Machine Learning")

        assert len(results) == 1


# ---------------------------------------------------------------------------
# query_event_dataset
# ---------------------------------------------------------------------------


class TestQueryEventDataset:
    """Verify the JSON-backed event database query helper."""

    @pytest.mark.asyncio
    async def test_filters_by_text_and_fields(self):
        events = [
            {
                "name": "AI Summit 2026",
                "category": "conference",
                "country": "US",
                "location": "San Francisco",
                "source": "Ticketmaster",
                "date": "2026-04-12",
            },
            {
                "name": "Summer Music Fest",
                "category": "music festival",
                "country": "US",
                "location": "Austin",
                "source": "Universe",
                "date": "2026-06-01",
            },
        ]

        with patch("mcp_server.server._load_event_dataset", return_value=events):
            from mcp_server.server import query_event_dataset
            results = await query_event_dataset(query="ai", category="conference", limit=5)

        assert len(results) == 1
        assert results[0]["name"] == "AI Summit 2026"

    @pytest.mark.asyncio
    async def test_limit_applies_after_filtering(self):
        events = [
            {
                "name": f"Event {idx}",
                "category": "conference",
                "country": "US",
                "location": "New York",
                "source": "Ticketmaster",
                "date": f"2026-01-0{idx}",
            }
            for idx in range(1, 4)
        ]

        with patch("mcp_server.server._load_event_dataset", return_value=events):
            from mcp_server.server import query_event_dataset
            results = await query_event_dataset(category="conference", limit=2)

        assert len(results) == 2
        assert results[0]["name"] == "Event 1"


# ---------------------------------------------------------------------------
# get_pricing_benchmark
# ---------------------------------------------------------------------------

class TestGetPricingBenchmark:
    """Verify pricing benchmark averaging logic."""

    @pytest.mark.asyncio
    async def test_averages_closest_models(self):
        benchmarks = [
            {"id": 1, "event_domain": "conference", "geography": "india",
             "audience_size": 900, "early_bird_usd": 100, "regular_usd": 200,
             "vip_usd": 500, "conversion_rate": 0.6, "size_diff": 100},
            {"id": 2, "event_domain": "conference", "geography": "india",
             "audience_size": 1100, "early_bird_usd": 120, "regular_usd": 240,
             "vip_usd": 600, "conversion_rate": 0.5, "size_diff": 100},
        ]
        fake_session = _make_fake_db_session(benchmarks)

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import get_pricing_benchmark
            result = await get_pricing_benchmark(
                domain="conference", geography="india", audience_size=1000
            )

        assert result["early_bird_avg"] == (100 + 120) // 2
        assert result["regular_avg"] == (200 + 240) // 2
        assert result["vip_avg"] == (500 + 600) // 2
        assert abs(result["conversion_avg"] - 0.55) < 0.01
        assert len(result["references"]) == 2

    @pytest.mark.asyncio
    async def test_no_benchmarks_returns_empty(self):
        fake_session = _make_fake_db_session([])

        with patch("mcp_server.server.session_factory", return_value=fake_session):
            from mcp_server.server import get_pricing_benchmark
            result = await get_pricing_benchmark(
                domain="obscure_domain", geography="mars", audience_size=10
            )

        assert result == {}
