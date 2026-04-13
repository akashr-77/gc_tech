"""
Unit tests for the generate_proposal and build_schedule MCP tools.
"""

import json
import pytest


# ---------------------------------------------------------------------------
# generate_proposal
# ---------------------------------------------------------------------------

class TestGenerateProposal:
    """Verify the sponsorship proposal generation tool."""

    @pytest.mark.asyncio
    async def test_basic_proposal_generation(self):
        from mcp_server.server import generate_proposal

        result = await generate_proposal(
            sponsor_name="TechCorp",
            event_name="AI Summit 2026",
            event_date="June 15-17, 2026",
            event_location="San Francisco, CA",
            tier="Platinum",
            amount_usd=150000,
            benefits=["Keynote slot", "Logo on main stage", "VIP lounge access"],
            audience_size=5000,
            event_domain="conference",
        )

        assert isinstance(result, str)
        # Check key content is present
        assert "TechCorp" in result
        assert "AI Summit 2026" in result
        assert "June 15-17, 2026" in result
        assert "San Francisco, CA" in result
        assert "Platinum" in result
        assert "$150,000 USD" in result
        assert "5,000" in result
        assert "Keynote slot" in result
        assert "Logo on main stage" in result
        assert "VIP lounge access" in result

    @pytest.mark.asyncio
    async def test_proposal_with_past_collaborations(self):
        from mcp_server.server import generate_proposal

        result = await generate_proposal(
            sponsor_name="GlobalBank",
            event_name="FinTech World 2026",
            event_date="September 1-3, 2026",
            event_location="London, UK",
            tier="Gold",
            amount_usd=75000,
            benefits=["Exhibition booth", "Panel seat", "Logo on website"],
            audience_size=3000,
            event_domain="conference",
            past_collaborations=[
                "FinTech World 2024 (Gold Sponsor)",
                "Banking Innovation Summit 2025 (Silver Sponsor)",
            ],
        )

        assert "Our Shared History" in result
        assert "GlobalBank" in result
        assert "FinTech World 2024 (Gold Sponsor)" in result
        assert "Banking Innovation Summit 2025 (Silver Sponsor)" in result

    @pytest.mark.asyncio
    async def test_proposal_without_past_collaborations(self):
        from mcp_server.server import generate_proposal

        result = await generate_proposal(
            sponsor_name="StartupInc",
            event_name="DevCon 2026",
            event_date="March 10, 2026",
            event_location="Austin, TX",
            tier="Silver",
            amount_usd=30000,
            benefits=["Logo on badge", "Social media mention"],
            audience_size=2000,
            event_domain="conference",
        )

        # No collaboration section when none provided
        assert "Our Shared History" not in result
        assert "StartupInc" in result
        assert "$30,000 USD" in result

    @pytest.mark.asyncio
    async def test_proposal_with_contact_name(self):
        from mcp_server.server import generate_proposal

        result = await generate_proposal(
            sponsor_name="MegaCorp",
            event_name="Cloud Expo 2026",
            event_date="November 5, 2026",
            event_location="Chicago, IL",
            tier="Platinum",
            amount_usd=200000,
            benefits=["Title sponsorship"],
            audience_size=8000,
            event_domain="conference",
            contact_name="Jane Smith",
        )

        assert "Dear Jane Smith," in result

    @pytest.mark.asyncio
    async def test_proposal_without_contact_name(self):
        from mcp_server.server import generate_proposal

        result = await generate_proposal(
            sponsor_name="DataCo",
            event_name="Data Summit 2026",
            event_date="July 20, 2026",
            event_location="New York, NY",
            tier="Gold",
            amount_usd=80000,
            benefits=["Booth space"],
            audience_size=4000,
            event_domain="conference",
        )

        assert "Dear DataCo Team," in result

    @pytest.mark.asyncio
    async def test_proposal_music_festival_domain(self):
        from mcp_server.server import generate_proposal

        result = await generate_proposal(
            sponsor_name="BeverageBrand",
            event_name="SoundWave Festival 2026",
            event_date="August 1-3, 2026",
            event_location="Miami, FL",
            tier="Gold",
            amount_usd=100000,
            benefits=["Stage naming rights", "Branded area"],
            audience_size=20000,
            event_domain="music_festival",
        )

        assert "Music Festival" in result
        assert "20,000" in result


# ---------------------------------------------------------------------------
# build_schedule
# ---------------------------------------------------------------------------

class TestBuildSchedule:
    """Verify the schedule builder with conflict detection."""

    @pytest.mark.asyncio
    async def test_simple_schedule_no_conflicts(self):
        from mcp_server.server import build_schedule

        sessions = [
            {"speaker": "Alice", "topic": "Intro to AI"},
            {"speaker": "Bob", "topic": "Cloud Computing"},
            {"speaker": "Carol", "topic": "Data Science"},
        ]
        rooms = ["Main Hall", "Room A"]
        time_slots = ["09:00-10:00", "10:00-11:00"]

        result = await build_schedule(
            sessions=sessions, rooms=rooms, time_slots=time_slots
        )

        assert result["summary"]["total_sessions"] == 3
        assert result["summary"]["assigned"] == 3
        assert result["summary"]["unassigned"] == 0
        assert result["summary"]["conflicts_detected"] == 0
        assert len(result["schedule"]) == 3
        assert len(result["conflicts"]) == 0
        assert len(result["unassigned"]) == 0

    @pytest.mark.asyncio
    async def test_speaker_conflict_detection(self):
        """Same speaker in two sessions should not be double-booked."""
        from mcp_server.server import build_schedule

        sessions = [
            {"speaker": "Alice", "topic": "Intro to AI"},
            {"speaker": "Alice", "topic": "Advanced AI"},
            {"speaker": "Bob", "topic": "Cloud Computing"},
        ]
        rooms = ["Main Hall"]
        time_slots = ["09:00-10:00", "10:00-11:00"]

        result = await build_schedule(
            sessions=sessions, rooms=rooms, time_slots=time_slots
        )

        # Alice's two sessions should be in different time slots
        alice_sessions = [s for s in result["schedule"] if s["speaker"] == "Alice"]
        if len(alice_sessions) == 2:
            assert alice_sessions[0]["time_slot"] != alice_sessions[1]["time_slot"]

        # All 3 sessions should fit: 1 room × 2 slots = 2, but we have 3 sessions
        # so Bob's session can't fit → one unassigned
        assert result["summary"]["total_sessions"] == 3
        assert result["summary"]["assigned"] == 2
        assert result["summary"]["unassigned"] == 1

    @pytest.mark.asyncio
    async def test_capacity_exceeded_conflict(self):
        """More sessions than room×slot capacity should report conflict."""
        from mcp_server.server import build_schedule

        sessions = [
            {"speaker": "Alice", "topic": "Topic A"},
            {"speaker": "Bob", "topic": "Topic B"},
            {"speaker": "Carol", "topic": "Topic C"},
            {"speaker": "Dave", "topic": "Topic D"},
            {"speaker": "Eve", "topic": "Topic E"},
        ]
        rooms = ["Room A"]
        time_slots = ["09:00-10:00", "10:00-11:00"]

        result = await build_schedule(
            sessions=sessions, rooms=rooms, time_slots=time_slots
        )

        assert result["summary"]["conflicts_detected"] > 0
        assert any("Capacity exceeded" in c for c in result["conflicts"])
        assert result["summary"]["unassigned"] == 3

    @pytest.mark.asyncio
    async def test_preferred_room_respected(self):
        """Sessions with preferred rooms should be placed there when possible."""
        from mcp_server.server import build_schedule

        sessions = [
            {"speaker": "Alice", "topic": "Keynote", "preferred_room": "Main Hall"},
            {"speaker": "Bob", "topic": "Workshop", "preferred_room": "Room B"},
        ]
        rooms = ["Main Hall", "Room B"]
        time_slots = ["09:00-10:00"]

        result = await build_schedule(
            sessions=sessions, rooms=rooms, time_slots=time_slots
        )

        assert result["summary"]["assigned"] == 2
        assert result["summary"]["conflicts_detected"] == 0

        alice_entry = next(s for s in result["schedule"] if s["speaker"] == "Alice")
        bob_entry = next(s for s in result["schedule"] if s["speaker"] == "Bob")
        assert alice_entry["room"] == "Main Hall"
        assert bob_entry["room"] == "Room B"

    @pytest.mark.asyncio
    async def test_multi_slot_duration(self):
        """Sessions requiring multiple consecutive slots are handled."""
        from mcp_server.server import build_schedule

        sessions = [
            {"speaker": "Alice", "topic": "Full Workshop", "duration_slots": 2},
            {"speaker": "Bob", "topic": "Quick Talk"},
        ]
        rooms = ["Main Hall"]
        time_slots = ["09:00-10:00", "10:00-11:00", "11:00-12:00"]

        result = await build_schedule(
            sessions=sessions, rooms=rooms, time_slots=time_slots
        )

        assert result["summary"]["assigned"] == 2
        assert result["summary"]["conflicts_detected"] == 0

        # Alice's workshop should span two slots
        alice_entry = next(s for s in result["schedule"] if s["speaker"] == "Alice")
        assert alice_entry["time_slot"] == "09:00-10:00 to 10:00-11:00"

    @pytest.mark.asyncio
    async def test_schedule_grid_structure(self):
        """The schedule_grid should have one row per time slot with room columns."""
        from mcp_server.server import build_schedule

        sessions = [
            {"speaker": "Alice", "topic": "Talk A"},
            {"speaker": "Bob", "topic": "Talk B"},
        ]
        rooms = ["Hall 1", "Hall 2"]
        time_slots = ["09:00-10:00", "10:00-11:00"]

        result = await build_schedule(
            sessions=sessions, rooms=rooms, time_slots=time_slots
        )

        grid = result["schedule_grid"]
        assert len(grid) == 2  # two time slots
        assert "time_slot" in grid[0]
        assert "Hall 1" in grid[0]
        assert "Hall 2" in grid[0]

    @pytest.mark.asyncio
    async def test_empty_sessions(self):
        """Empty session list should produce an empty schedule."""
        from mcp_server.server import build_schedule

        result = await build_schedule(
            sessions=[], rooms=["Room A"], time_slots=["09:00-10:00"]
        )

        assert result["summary"]["total_sessions"] == 0
        assert result["summary"]["assigned"] == 0
        assert len(result["conflicts"]) == 0

    @pytest.mark.asyncio
    async def test_room_not_double_booked(self):
        """Two sessions in the same time slot should go to different rooms."""
        from mcp_server.server import build_schedule

        sessions = [
            {"speaker": "Alice", "topic": "Talk A"},
            {"speaker": "Bob", "topic": "Talk B"},
        ]
        rooms = ["Room 1", "Room 2"]
        time_slots = ["09:00-10:00"]

        result = await build_schedule(
            sessions=sessions, rooms=rooms, time_slots=time_slots
        )

        assert result["summary"]["assigned"] == 2
        # Both should be in the same time slot but different rooms
        rooms_used = [s["room"] for s in result["schedule"]]
        assert len(set(rooms_used)) == 2
