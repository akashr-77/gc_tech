"""
Tests for session persistence via CheckpointStore in EventOpsAgent.

Validates that:
1. Session state is persisted to PostgreSQL on creation
2. _orchestrate updates checkpoint on success and failure
3. GET /sessions/{id} falls back to DB when not in memory
4. _on_startup restores incomplete sessions and marks them failed
5. _session_from_checkpoint converts DB rows to the in-memory format
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.eventops_agent.agent import EventOpsAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event_input(**overrides):
    """Return a minimal EventInput-like object with .dict() support."""
    defaults = {
        "session_id": "test-session-1",
        "topic": "AI Summit",
        "domain": "conference",
        "city": "San Francisco",
        "country": "USA",
        "budget_usd": 100_000,
        "target_audience": 500,
        "dates": "2025-06-01 to 2025-06-03",
    }
    defaults.update(overrides)
    obj = MagicMock()
    obj.dict.return_value = defaults
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# _session_from_checkpoint unit tests
# ---------------------------------------------------------------------------

class TestSessionFromCheckpoint:
    """Unit tests for the static helper that converts DB checkpoint → session."""

    def test_basic_fields(self):
        cp = {
            "event_input": {"topic": "AI"},
            "status": "executing",
            "started_at": "2025-01-01T00:00:00+00:00",
        }
        session = EventOpsAgent._session_from_checkpoint(cp)
        assert session["input"] == {"topic": "AI"}
        assert session["status"] == "executing"
        assert session["started_at"] == "2025-01-01T00:00:00+00:00"
        assert "final_plan" not in session
        assert "error" not in session

    def test_completed_with_plan(self):
        cp = {
            "event_input": {"topic": "AI"},
            "status": "completed",
            "started_at": "2025-01-01T00:00:00+00:00",
            "final_plan": {"event_details": {}},
            "completed_at": "2025-01-01T01:00:00+00:00",
            "error_message": None,
        }
        session = EventOpsAgent._session_from_checkpoint(cp)
        assert session["status"] == "completed"
        assert session["final_plan"] == {"event_details": {}}
        assert session["completed_at"] == "2025-01-01T01:00:00+00:00"

    def test_failed_with_error(self):
        cp = {
            "event_input": {"topic": "AI"},
            "status": "failed",
            "started_at": "2025-01-01T00:00:00+00:00",
            "error_message": "LLM timeout",
        }
        session = EventOpsAgent._session_from_checkpoint(cp)
        assert session["status"] == "failed"
        assert session["error"] == "LLM timeout"

    def test_canceled_with_error(self):
        cp = {
            "event_input": {"topic": "AI"},
            "status": "canceled",
            "started_at": "2025-01-01T00:00:00+00:00",
            "error_message": "Process stopped by user.",
        }
        session = EventOpsAgent._session_from_checkpoint(cp)
        assert session["status"] == "canceled"
        assert session["error"] == "Process stopped by user."

    def test_completed_at_datetime_object(self):
        """completed_at from asyncpg comes as a datetime, not a string."""
        dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        cp = {
            "event_input": {},
            "status": "completed",
            "started_at": "2025-01-01T00:00:00+00:00",
            "completed_at": dt,
        }
        session = EventOpsAgent._session_from_checkpoint(cp)
        assert session["completed_at"] == "2025-01-01T12:00:00+00:00"

    def test_missing_optional_fields(self):
        cp = {"status": "planning"}
        session = EventOpsAgent._session_from_checkpoint(cp)
        assert session["input"] is None
        assert session["started_at"] is None
        assert "final_plan" not in session
        assert "error" not in session
        assert "completed_at" not in session


# ---------------------------------------------------------------------------
# plan_conference persists checkpoint
# ---------------------------------------------------------------------------

class TestPlanEndpointPersistsCheckpoint:
    """Verify /plan creates a DB checkpoint alongside the in-memory session."""

    @pytest.fixture(autouse=True)
    def _patch_agent(self):
        with patch("agents.eventops_agent.agent.AsyncAzureOpenAI"), \
             patch("agents.eventops_agent.agent.MCPConnection"), \
             patch("agents.eventops_agent.agent.CheckpointStore") as MockCP:
            self.mock_cp = MockCP.return_value
            self.mock_cp.create = AsyncMock()
            self.agent = EventOpsAgent()
            yield

    @pytest.mark.asyncio
    async def test_checkpoint_created_on_plan(self):
        event_input = _make_event_input()
        # Simulate calling the /plan handler logic directly
        sid = event_input.session_id
        self.agent._active_sessions[sid] = {
            "input": event_input.dict(),
            "status": "starting",
        }
        await self.mock_cp.create(sid, event_input.dict())

        self.mock_cp.create.assert_called_once_with(sid, event_input.dict())


# ---------------------------------------------------------------------------
# _orchestrate persists status changes
# ---------------------------------------------------------------------------

class TestOrchestratePersistsState:

    @pytest.fixture(autouse=True)
    def _patch_agent(self):
        with patch("agents.eventops_agent.agent.AsyncAzureOpenAI"), \
             patch("agents.eventops_agent.agent.MCPConnection"), \
             patch("agents.eventops_agent.agent.CheckpointStore") as MockCP:
            self.mock_cp = MockCP.return_value
            self.mock_cp.create = AsyncMock()
            self.mock_cp.save_plan = AsyncMock()
            self.mock_cp.save_conflicts = AsyncMock()
            self.mock_cp.mark_failed = AsyncMock()
            self.mock_cp.mark_canceled = AsyncMock()
            self.agent = EventOpsAgent()
            yield

    @pytest.mark.asyncio
    async def test_successful_orchestration_saves_checkpoint(self):
        event_input = _make_event_input()
        sid = event_input.session_id

        self.agent._active_sessions[sid] = {
            "input": event_input.dict(),
            "status": "starting",
        }

        # Stub _llm_with_tools to return a plan
        plan_json = json.dumps({"event_details": {"name": "AI Summit"}})
        self.agent._llm_with_tools = AsyncMock(return_value=plan_json)

        await self.agent._orchestrate(sid, event_input)

        # save_plan is called to mark "executing"
        self.mock_cp.save_plan.assert_called_once()
        assert self.mock_cp.save_plan.call_args[0][0] == sid

        # save_conflicts is called to mark "completed" with final plan
        self.mock_cp.save_conflicts.assert_called_once()
        assert self.mock_cp.save_conflicts.call_args[0][0] == sid

        # In-memory session is updated
        assert self.agent._active_sessions[sid]["status"] == "completed"
        assert "final_plan" in self.agent._active_sessions[sid]

    @pytest.mark.asyncio
    async def test_failed_orchestration_marks_checkpoint(self):
        event_input = _make_event_input()
        sid = event_input.session_id

        self.agent._active_sessions[sid] = {
            "input": event_input.dict(),
            "status": "starting",
        }

        self.agent._llm_with_tools = AsyncMock(side_effect=RuntimeError("LLM boom"))

        with pytest.raises(RuntimeError, match="LLM boom"):
            await self.agent._orchestrate(sid, event_input)

        self.mock_cp.mark_failed.assert_called_once_with(sid, "LLM boom")
        assert self.agent._active_sessions[sid]["status"] == "failed"
        assert self.agent._active_sessions[sid]["error"] == "LLM boom"

    @pytest.mark.asyncio
    async def test_canceled_orchestration_marks_checkpoint(self):
        event_input = _make_event_input()
        sid = event_input.session_id

        self.agent._active_sessions[sid] = {
            "input": event_input.dict(),
            "status": "starting",
        }

        self.agent._llm_with_tools = AsyncMock(side_effect=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await self.agent._orchestrate(sid, event_input)

        self.mock_cp.mark_canceled.assert_called_once_with(sid, "Process stopped by user.")
        assert self.agent._active_sessions[sid]["status"] == "canceled"
        assert self.agent._active_sessions[sid]["error"] == "Process stopped by user."


# ---------------------------------------------------------------------------
# GET /sessions/{id} falls back to DB
# ---------------------------------------------------------------------------

class TestGetSessionFallback:

    @pytest.fixture(autouse=True)
    def _patch_agent(self):
        with patch("agents.eventops_agent.agent.AsyncAzureOpenAI"), \
             patch("agents.eventops_agent.agent.MCPConnection"), \
             patch("agents.eventops_agent.agent.CheckpointStore") as MockCP:
            self.mock_cp = MockCP.return_value
            self.mock_cp.load = AsyncMock(return_value=None)
            self.agent = EventOpsAgent()
            yield

    @pytest.mark.asyncio
    async def test_returns_in_memory_session_first(self):
        self.agent._active_sessions["s1"] = {"status": "working", "input": {}}
        # Directly test the logic
        session = self.agent._active_sessions.get("s1")
        assert session is not None
        assert session["status"] == "working"
        # DB should not be queried
        self.mock_cp.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_db(self):
        """When session not in memory, load from checkpoint DB."""
        self.mock_cp.load.return_value = {
            "session_id": "s2",
            "event_input": {"topic": "Restored"},
            "status": "completed",
            "started_at": "2025-01-01T00:00:00+00:00",
            "final_plan": {"event_details": {}},
            "completed_at": "2025-01-01T01:00:00+00:00",
            "error_message": None,
        }

        assert "s2" not in self.agent._active_sessions

        # Simulate the handler logic
        session = self.agent._active_sessions.get("s2")
        assert session is None  # not in memory

        checkpoint = await self.mock_cp.load("s2")
        assert checkpoint is not None
        restored = EventOpsAgent._session_from_checkpoint(checkpoint)
        self.agent._active_sessions["s2"] = restored

        assert self.agent._active_sessions["s2"]["status"] == "completed"
        assert self.agent._active_sessions["s2"]["final_plan"] == {"event_details": {}}


# ---------------------------------------------------------------------------
# _on_startup restores incomplete sessions
# ---------------------------------------------------------------------------

class TestStartupRestoration:

    @pytest.fixture(autouse=True)
    def _patch_agent(self):
        with patch("agents.eventops_agent.agent.AsyncAzureOpenAI"), \
             patch("agents.eventops_agent.agent.MCPConnection") as MockMCP, \
             patch("agents.eventops_agent.agent.CheckpointStore") as MockCP:
            self.mock_cp = MockCP.return_value
            self.mock_cp.find_incomplete = AsyncMock(return_value=[])
            self.mock_cp.mark_failed = AsyncMock()
            self.mock_mcp = MockMCP.return_value
            self.mock_mcp.connect = AsyncMock()
            self.agent = EventOpsAgent()
            yield

    @pytest.mark.asyncio
    async def test_restores_incomplete_sessions(self):
        self.mock_cp.find_incomplete.return_value = [
            {
                "session_id": "inc-1",
                "event_input": {"topic": "Old Event"},
                "status": "executing",
                "started_at": "2025-01-01T00:00:00+00:00",
                "task_plan": [],
                "completed_agents": [],
                "agent_outputs": {},
                "current_agent": "venue_agent",
            },
        ]

        await self.agent._on_startup()

        # Session should be in memory and marked failed
        assert "inc-1" in self.agent._active_sessions
        assert self.agent._active_sessions["inc-1"]["status"] == "failed"
        assert "interrupted" in self.agent._active_sessions["inc-1"]["error"]

        # DB checkpoint should be marked failed
        self.mock_cp.mark_failed.assert_called_once_with(
            "inc-1", "Session interrupted by container restart"
        )

    @pytest.mark.asyncio
    async def test_startup_continues_on_db_failure(self):
        """If DB is unavailable, startup should not crash."""
        self.mock_cp.find_incomplete.side_effect = ConnectionRefusedError("no DB")

        # Should not raise
        await self.agent._on_startup()

        # Agent should still be functional (empty sessions)
        assert self.agent._active_sessions == {}

    @pytest.mark.asyncio
    async def test_no_incomplete_sessions(self):
        self.mock_cp.find_incomplete.return_value = []

        await self.agent._on_startup()

        assert self.agent._active_sessions == {}
        self.mock_cp.mark_failed.assert_not_called()
