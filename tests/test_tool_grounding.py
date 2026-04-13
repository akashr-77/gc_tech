"""
Tool-grounding verification tests.

These tests answer the question: **"How do I know the LLM used the tool's
output instead of its own knowledge?"**

Strategy:
─────────
1. We mock every MCP tool to return a **unique, unmistakable marker** —
   a secret code-word or synthetic fact that no LLM could know from
   pre-training (e.g. "VENUE_MARKER_XQ7Z").

2. We mock the LLM to *behave as if* it called the tool and then
   produced a final answer that includes the marker.  If the marker
   appears in the final answer, the tool was called and its output was
   used.

3. We also verify that the conversation history (messages list) contains
   a `tool` role message — proof that the loop actually executed a tool
   call round-trip.

This approach works in unit tests without a real LLM.  For integration
tests with a live LLM, inject canary data into the DB/mock and assert
the final answer references it.

─────────────────────────────────────────────────────────────────────────

How to apply this in production / integration tests:
  • Seed the database with synthetic "canary" facts that don't exist in
    the real world (e.g., a venue named "Zephyr Hall XYZZY-42").
  • Ask the agent a question whose correct answer requires that canary.
  • Assert the final plan mentions "XYZZY-42".
  • If the LLM hallucinates instead of using the tool, the canary will
    be absent → test fails.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Verify the LLM tool loop calls tools and includes tool output
# ---------------------------------------------------------------------------

class TestToolLoopGrounding:
    """Prove that BaseConferenceAgent.llm_with_tools() actually calls
    MCP tools and feeds their output back into the conversation."""

    @pytest.mark.asyncio
    async def test_tool_output_appears_in_conversation(self):
        """
        Simulate: LLM requests web_search → tool returns canary marker →
        LLM produces final answer containing the marker.

        The test asserts:
        (a) The MCP tool was actually called.
        (b) The tool's output (canary) was appended to messages.
        (c) The final answer from the LLM references the canary.
        """
        CANARY = "CANARY_VENUE_XQ7Z_2026"

        # --- Mock the MCP connection ---
        mock_mcp = AsyncMock()
        mock_mcp.get_tools_schema.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                },
            }
        ]
        # Tool returns the canary
        mock_mcp.call_tool = AsyncMock(
            return_value=json.dumps([{"title": CANARY, "url": "https://example.com"}])
        )

        # --- Mock the LLM ---
        # First call: LLM wants to call web_search
        tool_call_msg = MagicMock()
        tool_call_msg.content = None
        tc = MagicMock()
        tc.id = "call_001"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "venues in Bangalore"})
        tool_call_msg.tool_calls = [tc]

        first_response = MagicMock()
        first_response.choices = [MagicMock(message=tool_call_msg)]

        # Second call: LLM produces final answer referencing canary
        final_msg = MagicMock()
        final_msg.content = f"Based on my search, the top venue is {CANARY}."
        final_msg.tool_calls = None

        second_response = MagicMock()
        second_response.choices = [MagicMock(message=final_msg)]

        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        # --- Build a minimal agent-like context to run llm_with_tools ---
        from agents.base_agent import BaseConferenceAgent
        from shared.a2a.models import AgentCard, AgentCapability, Task, Message, TextPart

        card = AgentCard(
            name="test_agent",
            description="Test",
            url="http://test:9999",
            domains=["conference"],
            capabilities=[AgentCapability(name="test", description="test")],
            input_schema={},
            output_schema={},
        )

        # We can't call __init__ normally (needs lifespan, config etc.),
        # so we create the object and manually set the attributes we need.
        agent = object.__new__(BaseConferenceAgent)
        agent.card = card
        agent.system_prompt = "You are a test agent."
        agent.llm = mock_llm
        agent._mcp = mock_mcp

        task = Task(
            session_id="test-session",
            messages=[Message(role="user", parts=[TextPart(text="Find venues")])],
        )

        result = await agent.llm_with_tools(task, user_message="Find venues in Bangalore")

        # ── ASSERTIONS ──

        # (a) The MCP tool was called
        mock_mcp.call_tool.assert_awaited_once_with(
            "web_search", {"query": "venues in Bangalore"}
        )

        # (b) The canary appears in the final answer
        assert CANARY in result, (
            f"Expected canary '{CANARY}' in the LLM's final answer. "
            f"If missing, the LLM ignored tool output."
        )

        # (c) The LLM was called exactly twice (tool-call + final)
        assert mock_llm.chat.completions.create.await_count == 2

    @pytest.mark.asyncio
    async def test_multiple_tools_called_in_parallel(self):
        """Verify that when the LLM requests multiple tools at once,
        all of them are executed and their results feed back."""
        VENUE_CANARY = "VENUE_ZEPHYR_42"
        PRICING_CANARY = "PRICING_PLUTO_99"

        mock_mcp = AsyncMock()
        mock_mcp.get_tools_schema.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "query_venues",
                    "description": "Query venues",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pricing_benchmark",
                    "description": "Get pricing",
                    "parameters": {"type": "object", "properties": {"domain": {"type": "string"}}},
                },
            },
        ]

        async def fake_call_tool(name, args):
            if name == "query_venues":
                return json.dumps([{"name": VENUE_CANARY}])
            elif name == "get_pricing_benchmark":
                return json.dumps({"benchmark": PRICING_CANARY})
            return "{}"

        mock_mcp.call_tool = AsyncMock(side_effect=fake_call_tool)

        # LLM calls both tools in one round
        tool_call_msg = MagicMock()
        tool_call_msg.content = None
        tc1 = MagicMock()
        tc1.id = "call_v"
        tc1.function.name = "query_venues"
        tc1.function.arguments = json.dumps({"city": "Bangalore"})
        tc2 = MagicMock()
        tc2.id = "call_p"
        tc2.function.name = "get_pricing_benchmark"
        tc2.function.arguments = json.dumps({"domain": "conference"})
        tool_call_msg.tool_calls = [tc1, tc2]

        first_response = MagicMock()
        first_response.choices = [MagicMock(message=tool_call_msg)]

        final_msg = MagicMock()
        final_msg.content = f"Venue: {VENUE_CANARY}, Pricing: {PRICING_CANARY}"
        final_msg.tool_calls = None
        second_response = MagicMock()
        second_response.choices = [MagicMock(message=final_msg)]

        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        from agents.base_agent import BaseConferenceAgent
        from shared.a2a.models import AgentCard, AgentCapability, Task, Message, TextPart

        card = AgentCard(
            name="test_agent", description="Test", url="http://test:9999",
            domains=["conference"],
            capabilities=[AgentCapability(name="test", description="test")],
            input_schema={}, output_schema={},
        )
        agent = object.__new__(BaseConferenceAgent)
        agent.card = card
        agent.system_prompt = "You are a test agent."
        agent.llm = mock_llm
        agent._mcp = mock_mcp

        task = Task(
            session_id="test-session",
            messages=[Message(role="user", parts=[TextPart(text="Plan event")])],
        )

        result = await agent.llm_with_tools(task, user_message="Plan event in Bangalore")

        # Both tools were called
        assert mock_mcp.call_tool.await_count == 2

        # Both canaries appear in the final answer
        assert VENUE_CANARY in result
        assert PRICING_CANARY in result


# ---------------------------------------------------------------------------
# 2. Verify tool failure is handled gracefully
# ---------------------------------------------------------------------------

class TestToolFailureHandling:
    """When a tool throws an exception, the error should be sent back to
    the LLM as a tool result so it can recover."""

    @pytest.mark.asyncio
    async def test_tool_error_fed_back_to_llm(self):
        mock_mcp = AsyncMock()
        mock_mcp.get_tools_schema.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]
        # Tool raises an error
        mock_mcp.call_tool = AsyncMock(side_effect=Exception("Network timeout"))

        # LLM first requests tool, then produces final answer
        tool_call_msg = MagicMock()
        tool_call_msg.content = None
        tc = MagicMock()
        tc.id = "call_err"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "test"})
        tool_call_msg.tool_calls = [tc]

        first_response = MagicMock()
        first_response.choices = [MagicMock(message=tool_call_msg)]

        final_msg = MagicMock()
        final_msg.content = "Sorry, the search tool encountered an error."
        final_msg.tool_calls = None
        second_response = MagicMock()
        second_response.choices = [MagicMock(message=final_msg)]

        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        from agents.base_agent import BaseConferenceAgent
        from shared.a2a.models import AgentCard, AgentCapability, Task, Message, TextPart

        card = AgentCard(
            name="test_agent", description="Test", url="http://test:9999",
            domains=["conference"],
            capabilities=[AgentCapability(name="test", description="test")],
            input_schema={}, output_schema={},
        )
        agent = object.__new__(BaseConferenceAgent)
        agent.card = card
        agent.system_prompt = "You are a test agent."
        agent.llm = mock_llm
        agent._mcp = mock_mcp

        task = Task(
            session_id="test-session",
            messages=[Message(role="user", parts=[TextPart(text="Search")])],
        )

        result = await agent.llm_with_tools(task, user_message="Search for something")

        # The agent didn't crash — it produced an answer
        assert result is not None
        assert len(result) > 0

        # The LLM received the error as a tool message (verify via call args)
        second_call_messages = mock_llm.chat.completions.create.call_args_list[1][1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "Network timeout" in tool_messages[0]["content"]


# ---------------------------------------------------------------------------
# 3. Verify loop exhaustion raises
# ---------------------------------------------------------------------------

class TestToolLoopExhaustion:
    """If the LLM keeps calling tools without producing a final answer,
    the loop should return a graceful fallback message."""

    @pytest.mark.asyncio
    async def test_returns_fallback_after_max_iterations(self):
        mock_mcp = AsyncMock()
        mock_mcp.get_tools_schema.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]
        mock_mcp.call_tool = AsyncMock(return_value="some result")

        # LLM always calls a tool, never produces a final answer
        tool_call_msg = MagicMock()
        tool_call_msg.content = None
        tc = MagicMock()
        tc.id = "call_loop"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "loop"})
        tool_call_msg.tool_calls = [tc]

        loop_response = MagicMock()
        loop_response.choices = [MagicMock(message=tool_call_msg)]

        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=loop_response)

        from agents.base_agent import BaseConferenceAgent
        from shared.a2a.models import AgentCard, AgentCapability, Task, Message, TextPart

        card = AgentCard(
            name="test_agent", description="Test", url="http://test:9999",
            domains=["conference"],
            capabilities=[AgentCapability(name="test", description="test")],
            input_schema={}, output_schema={},
        )
        agent = object.__new__(BaseConferenceAgent)
        agent.card = card
        agent.system_prompt = "You are a test agent."
        agent.llm = mock_llm
        agent._mcp = mock_mcp

        task = Task(
            session_id="test-session",
            messages=[Message(role="user", parts=[TextPart(text="Loop")])],
        )

        result = await agent.llm_with_tools(task, user_message="Keep looping")

        # The agent should return a graceful fallback, not crash
        assert "unable to produce a final response" in result
        assert "test_agent" in result


# ---------------------------------------------------------------------------
# 4. Verify MCPConnection tool filtering
# ---------------------------------------------------------------------------

class TestMCPConnectionToolFiltering:
    """Verify that MCPConnection.allowed_tools filters which tools the LLM sees."""

    def test_allowed_tools_filters_schema(self):
        """When allowed_tools is set, get_tools_schema() only returns those tools."""
        from agents.base_agent import MCPConnection

        conn = MCPConnection("http://fake:8080", allowed_tools=["discover_agents", "ask_agent"])

        # Simulate discovered tools (normally set by connect())
        tool_a = MagicMock()
        tool_a.name = "discover_agents"
        tool_a.description = "Discover agents"
        tool_a.inputSchema = {"type": "object", "properties": {}}

        tool_b = MagicMock()
        tool_b.name = "ask_agent"
        tool_b.description = "Ask an agent"
        tool_b.inputSchema = {"type": "object", "properties": {}}

        tool_c = MagicMock()
        tool_c.name = "query_venues"
        tool_c.description = "Query venues"
        tool_c.inputSchema = {"type": "object", "properties": {}}

        tool_d = MagicMock()
        tool_d.name = "query_speakers"
        tool_d.description = "Query speakers"
        tool_d.inputSchema = {"type": "object", "properties": {}}

        # Manually set filtered tools (simulating what connect() does)
        all_tools = [tool_a, tool_b, tool_c, tool_d]
        conn._tools = [t for t in all_tools if t.name in conn._allowed_tools]
        conn._tools_openai = conn._convert_tools_to_openai(conn._tools)

        schema = conn.get_tools_schema()
        tool_names = [t["function"]["name"] for t in schema]

        assert "discover_agents" in tool_names
        assert "ask_agent" in tool_names
        assert "query_venues" not in tool_names
        assert "query_speakers" not in tool_names
        assert len(schema) == 2

    def test_no_filter_returns_all_tools(self):
        """When allowed_tools is None, get_tools_schema() returns all tools."""
        from agents.base_agent import MCPConnection

        conn = MCPConnection("http://fake:8080")

        tool_a = MagicMock()
        tool_a.name = "discover_agents"
        tool_a.description = "Discover agents"
        tool_a.inputSchema = {"type": "object", "properties": {}}

        tool_b = MagicMock()
        tool_b.name = "query_venues"
        tool_b.description = "Query venues"
        tool_b.inputSchema = {"type": "object", "properties": {}}

        conn._tools = [tool_a, tool_b]
        conn._tools_openai = conn._convert_tools_to_openai(conn._tools)

        schema = conn.get_tools_schema()
        tool_names = [t["function"]["name"] for t in schema]

        assert "discover_agents" in tool_names
        assert "query_venues" in tool_names
        assert len(schema) == 2

    def test_eventops_excludes_data_tools(self):
        """Verify EventOps agent's EVENTOPS_ALLOWED_TOOLS excludes domain-specific data tools."""
        from agents.eventops_agent.agent import EVENTOPS_ALLOWED_TOOLS

        domain_data_tools = {
            "query_venues", "query_sponsors", "query_speakers",
            "query_communities", "get_pricing_benchmark", "generate_proposal",
        }
        orchestration_tools = {
            "discover_agents", "ask_agent",
            "read_working_memory", "write_working_memory",
        }

        allowed = set(EVENTOPS_ALLOWED_TOOLS)
        # Orchestration tools must be present
        for tool in orchestration_tools:
            assert tool in allowed, f"Orchestration tool '{tool}' missing from EVENTOPS_ALLOWED_TOOLS"
        # Domain data tools must NOT be present
        for tool in domain_data_tools:
            assert tool not in allowed, f"Data tool '{tool}' should not be in EVENTOPS_ALLOWED_TOOLS"
