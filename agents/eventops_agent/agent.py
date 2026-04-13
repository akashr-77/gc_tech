import json
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncAzureOpenAI, RateLimitError
from shared.a2a.models import (
    AgentCard, AgentCapability, Task, Artifact,
    TextPart, EventInput
)
from shared.a2a.server import A2AServer
from shared.config import config
from shared.memory.checkpoint import CheckpointStore
from agents.base_agent import MCPConnection, extract_json

# Retry settings for rate-limit (429) handling
MAX_RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BASE_DELAY = 2  # seconds
MAX_TOOL_LOOP_ITERATIONS = 25
MAX_TOOL_RESULT_CHARS = 20000  # truncate individual tool results to stay within token limits

CARD = AgentCard(
    name="eventops_agent",
    description="Autonomous orchestrator: uses MCP tools to discover agents, delegate tasks, and compile a final event plan",
    url="http://eventops-agent:8000",
    domains=["conference", "music_festival", "sporting_event"],
    capabilities=[
        AgentCapability(name="orchestration", description="Autonomously discover and coordinate specialist agents"),
        AgentCapability(name="output_merging", description="Compile all agent outputs into a unified event plan"),
    ],
    input_schema={
        "topic": "string",
        "domain": "string",
        "city": "string",
        "country": "string",
        "budget_usd": "number",
        "target_audience": "number",
        "dates": "string"
    },
    output_schema={"conference_plan": "object"}
)

# Orchestration tools that EventOps is allowed to see.  Domain-specific data
# tools (query_venues, query_speakers, …) are intentionally excluded so the
# LLM is forced to delegate those lookups to specialist agents via ask_agent.
EVENTOPS_ALLOWED_TOOLS: list[str] = [
    # Agent discovery & communication
    "discover_agents",
    "ask_agent",
    # Shared working memory
    "read_working_memory",
    "write_working_memory",
    # Episodic / procedural memory
    "vector_search",
    "write_memory",
    "query_past_experiences",
    "query_guidelines_and_rules",
    # Schedule builder (used directly by EventOps per its workflow)
    "build_schedule",
    # General web research (not domain-specific)
    "web_search",
    "scrape_page",
]

SYSTEM_PROMPT = """You are the EventOps Agent — the master orchestrator for event planning.

You have access to MCP tools that let you discover peer agents, communicate with them,
and manage shared working memory. You must use these tools autonomously to plan the event.

## Your Workflow

1. **Discover agents**: Use the `discover_agents` tool to find which specialist agents are
   available (venue, pricing, speaker, sponsor, exhibitor, community, etc.).

2. **Delegate tasks**: Use the `ask_agent` tool to send questions/tasks to the specialist
   agents you discovered. Each agent is autonomous and will use its own tools and reasoning.
   You can call multiple agents — call them with clear, specific prompts that include the
   full event context (session_id, topic, city, budget, audience, dates).
   IMPORTANT: Call ALL relevant agents in a single response so they execute in parallel.
   Do NOT call them one at a time across separate responses.

3. **Check working memory**: Use `read_working_memory` to see what agents have written.
   Agents write their findings to working memory as they work. You can use this to check
   progress or get outputs from agents.

4. **Write working memory**: Use `write_working_memory` to share your own orchestration
   decisions or compiled results.

5. **Compile the final plan**: After gathering outputs from all relevant agents, compile
   everything into a single cohesive event plan.

6. **Build the event schedule**: Use the `build_schedule` tool to create a conflict-free
   time-slotted schedule from the speaker-topic assignments. Provide:
   - A list of sessions (speaker + topic pairs from the speaker agent)
   - Available rooms (from the venue agent's room/hall information)
   - Time slots for the event days
   The tool will detect conflicts (same speaker in two sessions, room double-booking)
   and produce a schedule grid. Include the schedule in the final plan.

## CRITICAL: Quality Validation Before Compiling

Before producing the final plan, you MUST validate each agent's output:

### No Lazy Outputs
If any agent returned a placeholder instead of real data (e.g., "saved to working memory",
"plan to be developed later", "see details in memory"), you MUST either:
- Re-ask that agent with a more specific prompt demanding the actual data, OR
- Read that agent's working memory entries and include the actual data yourself.
NEVER pass through placeholder text in the final plan.

### Price Sanity Check
Cross-check venue prices against common sense:
- A large banquet/conference venue in a major city costs $3,000 to $50,000/day, NOT $50/day.
- If a venue price seems absurdly low or high, flag it as "unverified" or discard it.

### Currency Standardization
ALL monetary values in the final plan MUST be in USD. If an agent returned values in
local currency (INR, EUR, etc.), convert them to USD. Label every amount clearly:
"$X USD" or "$X USD (approx ₹Y INR)".

## Episodic Memory
After compiling the final plan, you MUST use the `write_memory` tool to save orchestration
insights. This is NOT optional — call write_memory at least once before returning. For example:
- Which agents provided the most useful outputs
- Any coordination issues or dependencies between agents
- Patterns that could improve future event planning
Save to namespace "eventops_agent" with metadata including the city, domain, and a short category tag.

## Important Guidelines

- Do NOT hardcode which agents exist. Always discover them dynamically.
- Do NOT skip agents — delegate to all relevant specialist agents.
- Always include the session_id when calling `ask_agent` or working memory tools.
- If an agent fails, note the failure and continue with the others.
- When asking agents, provide the full event context so they have everything they need.
- After collecting all agent outputs, compile them into a unified JSON plan covering:
  venue selection, ticket pricing, speaker lineup, sponsor recommendations,
  exhibitor floor plan, and community/GTM strategy.

## Output Format — MANDATORY
Return ONLY the raw JSON object. Do NOT include:
- Any text before or after the JSON (no "Here is the plan..." preamble)
- Markdown code fences (no ```json``` wrappers)
- Commentary or explanation outside the JSON structure

Your entire response must be parseable by json.loads() with no preprocessing.
The JSON must follow this exact top-level structure:
{
  "event_details": { ... },
  "venue_options": [ ... ],
  "ticket_pricing_tiers": [ ... ],
  "revenue_forecast_usd": <number>,
  "speakers": [ ... ],
  "schedule": { "schedule_grid": [...], "conflicts": [...] },
  "sponsors": [ ... ],
  "exhibitors": [ ... ],
  "community_gtm_strategy": { ... }
}
"""


class EventOpsAgent(A2AServer):

    def __init__(self):
        @asynccontextmanager
        async def _lifespan(app):
            await self._on_startup()
            yield
            await self._on_shutdown()

        super().__init__(CARD, lifespan=_lifespan)

        # Allow cross-origin requests so the frontend can call the API directly.
        # Restrict to specific origins in production by setting the
        # CORS_ALLOWED_ORIGINS environment variable (comma-separated list).
        # Default: allow all origins (suitable for local dev / initial deploy).
        _raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*")
        _allowed_origins = (
            ["*"] if _raw_origins == "*"
            else [o.strip() for o in _raw_origins.split(",") if o.strip()]
        )
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=_allowed_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.llm = AsyncAzureOpenAI(
            azure_endpoint=config.azure_openai_endpoint,
            api_key=config.azure_openai_api_key,
            api_version=config.azure_openai_api_version
        )
        self._active_sessions: dict[str, dict] = {}
        # EventOps only gets orchestration tools — NOT domain-specific data
        # tools like query_venues, query_speakers, etc.  This forces the LLM
        # to delegate data lookups to specialist agents via ask_agent instead
        # of short-circuiting them by querying the database directly.
        self._mcp = MCPConnection(config.mcp_server_url, allowed_tools=EVENTOPS_ALLOWED_TOOLS)
        self._checkpoint = CheckpointStore()

        # ─── API Routes ──────────────────────────────────────────────────

        @self.app.post("/plan")
        async def plan_conference(event_input: EventInput, background_tasks: BackgroundTasks):
            session_id = event_input.session_id or str(uuid.uuid4())
            self._active_sessions[session_id] = {
                "input": event_input.dict(),
                "status": "starting",
                "started_at": datetime.now(timezone.utc).isoformat()
            }
            await self._checkpoint.create(session_id, event_input.dict())
            background_tasks.add_task(self._orchestrate, session_id, event_input)
            return {"session_id": session_id, "status": "started"}

        @self.app.get("/sessions/{session_id}")
        async def get_session(session_id: str):
            session = self._active_sessions.get(session_id)
            if session is not None:
                return session
            # Fall back to checkpoint stored in PostgreSQL
            checkpoint = await self._checkpoint.load(session_id)
            if checkpoint is not None:
                session = self._session_from_checkpoint(checkpoint)
                self._active_sessions[session_id] = session
                return session
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    # ─── Startup / Shutdown ──────────────────────────────────────────────────

    async def _on_startup(self):
        """Connect to MCP server and restore sessions from checkpoint DB on startup."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                await self._mcp.connect()
                break
            except Exception as e:
                wait = 2 ** attempt
                print(f"[EventOps] MCP connection attempt {attempt+1}/{max_retries} "
                      f"failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
        else:
            raise RuntimeError(
                f"[EventOps] FATAL: Could not connect to MCP server after "
                f"{max_retries} attempts."
            )

        # Restore persisted sessions from PostgreSQL checkpoints
        try:
            incomplete = await self._checkpoint.find_incomplete()
            for cp in incomplete:
                sid = cp["session_id"]
                self._active_sessions[sid] = self._session_from_checkpoint(cp)
                # Mark interrupted sessions so callers know they didn't finish
                if cp["status"] in ("planning", "executing"):
                    await self._checkpoint.mark_failed(
                        sid, "Session interrupted by container restart"
                    )
                    self._active_sessions[sid]["status"] = "failed"
                    self._active_sessions[sid]["error"] = (
                        "Session interrupted by container restart"
                    )
            if incomplete:
                print(
                    f"[EventOps] Restored {len(incomplete)} session(s) from checkpoint DB."
                )
        except Exception as e:
            # Non-fatal: if DB is unavailable we can still serve new requests
            print(f"[EventOps] WARNING: Failed to restore sessions from DB: {e}")

    async def _on_shutdown(self):
        await self._mcp.disconnect()

    # ─── Checkpoint ↔ Session Conversion ────────────────────────────────────

    @staticmethod
    def _session_from_checkpoint(cp: dict) -> dict:
        """Convert a checkpoint row (from PostgreSQL) to the in-memory session format."""
        session: dict = {
            "input": cp.get("event_input"),
            "status": cp.get("status", "unknown"),
            "started_at": cp.get("started_at"),
        }
        if cp.get("final_plan"):
            session["final_plan"] = cp["final_plan"]
        if cp.get("error_message"):
            session["error"] = cp["error_message"]
        completed_at = cp.get("completed_at")
        if completed_at:
            session["completed_at"] = (
                completed_at if isinstance(completed_at, str)
                else completed_at.isoformat()
            )
        return session

    # ─── LLM Tool Loop ──────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_assistant_message(msg) -> dict:
        """Build a clean assistant message dict for Azure OpenAI."""
        sanitized: dict = {"role": "assistant"}
        if msg.content is not None:
            sanitized["content"] = msg.content
        if msg.tool_calls:
            sanitized["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return sanitized

    async def _llm_create_with_retry(self, *, messages, tools):
        """Call the LLM with automatic retry on 429 rate-limit errors."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES):
            try:
                return await self.llm.chat.completions.create(
                    model=config.model,
                    max_tokens=16384,
                    messages=messages,
                    **({"tools": tools} if tools else {}),
                )
            except RateLimitError as exc:
                if attempt == MAX_RATE_LIMIT_RETRIES - 1:
                    raise
                delay = RATE_LIMIT_BASE_DELAY * (2 ** attempt)
                print(
                    f"[EventOps] Rate-limited (429). "
                    f"Retrying in {delay}s (attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})…"
                )
                await asyncio.sleep(delay)

    async def _llm_with_tools(self, user_message: str) -> str:
        """Run the LLM in an autonomous tool-use loop.

        All tools come from MCP — including discover_agents, ask_agent,
        working memory, web search, and database queries.
        The LLM autonomously decides which tools to call and when.
        Returns the LLM's final text response.
        """
        tools_schema = self._mcp.get_tools_schema()
        if not tools_schema:
            print("[EventOps] WARNING: No tool schemas available from MCP.")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]

        for iteration in range(MAX_TOOL_LOOP_ITERATIONS):
            is_penultimate = iteration == MAX_TOOL_LOOP_ITERATIONS - 2

            response = await self._llm_create_with_retry(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            )

            msg = response.choices[0].message

            # If the LLM returned final text (no tool calls) → done
            if not msg.tool_calls:
                return msg.content or ""

            # On the penultimate iteration, warn and prepare to force a final answer
            if is_penultimate:
                print(
                    f"[EventOps] Approaching tool loop limit "
                    f"({MAX_TOOL_LOOP_ITERATIONS}). Next call will be without tools."
                )

            # LLM wants to call tools → execute them all concurrently via MCP
            messages.append(self._sanitize_assistant_message(msg))

            async def _exec_tool(tc):
                try:
                    call_args = json.loads(tc.function.arguments)
                    print(
                        f"[EventOps] 🛠️  Calling MCP tool '{tc.function.name}' "
                        f"with args: {tc.function.arguments}"
                    )
                    result = await self._mcp.call_tool(tc.function.name, call_args)
                except Exception as e:
                    print(
                        f"[EventOps] ⚠️  Tool '{tc.function.name}' failed "
                        f"(args: {tc.function.arguments}): {e}"
                    )
                    result = json.dumps({"error": str(e)})
                content = result if isinstance(result, str) else json.dumps(result)
                if len(content) > MAX_TOOL_RESULT_CHARS:
                    content = content[:MAX_TOOL_RESULT_CHARS - 16] + "\n... [truncated]"
                return {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content
                }

            tool_results = await asyncio.gather(
                *[_exec_tool(tc) for tc in msg.tool_calls]
            )
            messages.extend(tool_results)

            # If we've reached the penultimate iteration, strip tools so the
            # LLM is forced to produce a final text response.
            if is_penultimate:
                tools_schema = None

        # Should not normally be reached because the last iteration has no
        # tools, but handle gracefully just in case.
        print(
            f"[EventOps] WARNING: LLM tool loop exhausted {MAX_TOOL_LOOP_ITERATIONS} "
            f"iterations without producing a final response. Returning partial summary."
        )
        return (
            f"[EventOps] was unable to produce a final response within "
            f"{MAX_TOOL_LOOP_ITERATIONS} iterations. Please review partial results in working memory."
        )

    # ─── JSON Extraction ────────────────────────────────────────────────────

    # Delegate to the shared module-level extract_json function
    _extract_json = staticmethod(extract_json)

    # ─── Main Orchestration ──────────────────────────────────────────────────

    async def _orchestrate(self, session_id: str, event_input: EventInput):
        """Let the LLM autonomously orchestrate the event planning.

        The LLM uses MCP tools (discover_agents, ask_agent, working memory,
        etc.) to discover agents, delegate tasks, gather results, and compile
        the final event plan — all without hardcoded logic."""
        session = self._active_sessions[session_id]
        user_message = (
            f"Plan the following event. Use the MCP tools to discover available "
            f"specialist agents, delegate tasks to each of them, and compile "
            f"their outputs into a final unified event plan.\n\n"
            f"Session ID: {session_id}\n"
            f"Event: {event_input.topic} ({event_input.domain})\n"
            f"Location: {event_input.city}, {event_input.country}\n"
            f"Budget: ${event_input.budget_usd:,} USD\n"
            f"Target audience: {event_input.target_audience}\n"
            f"Dates: {event_input.dates}\n\n"
            f"IMPORTANT: All monetary values in the final plan must be in USD."
        )

        try:
            session["status"] = "working"
            await self._checkpoint.save_plan(session_id, [
                {"agent": "llm_orchestrator", "task": "autonomous_tool_loop",
                 "status": "executing"}
            ])
            raw_plan = await self._llm_with_tools(user_message)
            session["final_plan"] = self._extract_json(raw_plan)
            session["status"] = "completed"
            session["completed_at"] = datetime.now(timezone.utc).isoformat()
            await self._checkpoint.save_conflicts(session_id, session["final_plan"]
                                                  if isinstance(session["final_plan"], dict)
                                                  else {"result": session["final_plan"]})

        except Exception as e:
            session["status"] = "failed"
            session["error"] = str(e)
            await self._checkpoint.mark_failed(session_id, str(e))
            raise

    # ─── A2A Task Handler ────────────────────────────────────────────────────

    async def handle_task(self, task: Task) -> dict:
        """Handle incoming A2A tasks autonomously using the LLM tool loop."""
        user_message = ""
        if task.messages and task.messages[0].parts:
            user_message = task.messages[0].parts[0].text

        result = await self._llm_with_tools(user_message)
        artifact = Artifact(
            name="eventops_response",
            parts=[TextPart(text=result)]
        )
        return {"artifact": artifact}