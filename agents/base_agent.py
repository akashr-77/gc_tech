import json
import asyncio
import re
import httpx
from contextlib import asynccontextmanager
from openai import AsyncAzureOpenAI, RateLimitError
from mcp import ClientSession
from mcp.client.sse import sse_client
from shared.a2a.server import A2AServer
from shared.a2a.models import Task
from shared.config import config

# Retry settings for rate-limit (429) handling
MAX_RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BASE_DELAY = 2  # seconds
MAX_TOOL_RESULT_CHARS = 20000  # truncate individual tool results to stay within token limits

# Regex for matching markdown code fences: ```json ... ``` or ``` ... ```
# Uses word boundary (?!\w) after the optional 'json' tag to avoid matching 'javascript' etc.
_JSON_FENCE_PATTERN = re.compile(r"```(?:json(?!\w))?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def extract_json(raw: str) -> dict | str:
    """Extract clean JSON from an LLM's raw response.

    Handles common LLM formatting issues:
    - Preamble text before the JSON (e.g. "Here is the plan...")
    - Markdown code fences (```json ... ```)
    - Trailing text after the JSON

    Returns the parsed dict when valid JSON is found, or the
    original string if no valid JSON could be extracted.
    """
    # 1. Strip markdown code fences
    fenced = _JSON_FENCE_PATTERN.search(raw)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. Find the outermost JSON object by brace matching
    start = raw.find("{")
    if start != -1:
        depth = 0
        end = start
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        candidate = raw[start:end + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Fallback: return original string
    return raw


class MCPConnection:
    """
    Manages a persistent connection to the MCP server over SSE.
    Handles tool discovery, tool calls, and automatic reconnection.
    """

    def __init__(self, server_url: str, allowed_tools: list[str] | None = None):
        self.server_url = server_url
        self._allowed_tools = set(allowed_tools) if allowed_tools else None
        self._session: ClientSession | None = None
        self._tools: list[dict] | None = None
        self._tools_openai: list[dict] | None = None
        self._connected = False
        # Context managers that must stay alive for the session
        self._sse_cm = None
        self._session_cm = None

    async def connect(self):
        """Connect to the MCP server over SSE and discover tools."""
        if self._connected and self._session:
            return

        print(f"[MCP] Connecting to {self.server_url} ...")

        # Open the SSE transport — this returns context managers we must hold
        self._sse_cm = sse_client(self.server_url)
        read, write = await self._sse_cm.__aenter__()

        # Open the client session over the transport
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()

        # Perform the MCP handshake
        await self._session.initialize()

        # Discover available tools from the server
        tools_response = await self._session.list_tools()
        all_tools = tools_response.tools

        # If an allow-list was provided, only expose those tools to the LLM.
        # Note: call_tool() talks to the MCP session directly, so it can
        # still invoke any server-side tool regardless of this filter.
        if self._allowed_tools:
            self._tools = [t for t in all_tools if t.name in self._allowed_tools]
        else:
            self._tools = all_tools
        self._tools_openai = self._convert_tools_to_openai(self._tools)
        self._connected = True

        all_names = [t.name for t in all_tools]
        exposed_names = [t.name for t in self._tools]
        print(f"[MCP] Connected. Discovered {len(all_tools)} tools: {all_names}")
        if self._allowed_tools:
            print(f"[MCP] Tool filter active. Exposing {len(self._tools)} tools: {exposed_names}")

    async def disconnect(self):
        """Cleanly close the MCP connection."""
        try:
            if self._session_cm:
                await self._session_cm.__aexit__(None, None, None)
            if self._sse_cm:
                await self._sse_cm.__aexit__(None, None, None)
        except Exception as e:
            print(f"[MCP] Error during disconnect: {e}")
        finally:
            self._session = None
            self._connected = False

    async def ensure_connected(self):
        """Reconnect if the connection was lost."""
        if not self._connected or not self._session:
            await self.connect()

    @staticmethod
    def _extract_result(result) -> str:
        """Extract text/data from an MCP tool result content list."""
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            elif hasattr(content, "data"):
                parts.append(json.dumps(content.data))

        if not parts:
            return str(result)
        if len(parts) == 1:
            return parts[0]

        # Multiple content parts: combine into a JSON array when every
        # part is individually valid JSON (e.g. discover_agents returning
        # one object per content part).  Fall back to newline-joining for
        # non-JSON content.
        json_items = []
        all_json = True
        for p in parts:
            try:
                json_items.append(json.loads(p))
            except (json.JSONDecodeError, TypeError):
                all_json = False
                break

        if all_json:
            return json.dumps(json_items)

        return "\n".join(parts)

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on the MCP server and return the result as a string."""
        await self.ensure_connected()

        try:
            result = await self._session.call_tool(tool_name, arguments=arguments)
            return self._extract_result(result)

        except Exception as e:
            # Try reconnecting once on failure
            print(f"[MCP] Tool call failed ({tool_name}): {e}. Reconnecting...")
            self._connected = False
            await self.connect()
            result = await self._session.call_tool(tool_name, arguments=arguments)
            return self._extract_result(result)

    def get_tools_schema(self) -> list[dict]:
        """Get all tool schemas in OpenAI format."""
        return self._tools_openai or []

    @staticmethod
    def _convert_tools_to_openai(mcp_tools: list) -> list[dict]:
        """
        Convert MCP tool schemas to OpenAI tool format.
        MCP tools have: name, description, inputSchema
        OpenAI wants: type='function', function={name, description, parameters}
        """
        openai_tools = []
        for tool in mcp_tools:
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or f"MCP tool: {tool.name}",
                    "parameters": tool.inputSchema if hasattr(tool, "inputSchema") else {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
            openai_tools.append(schema)
        return openai_tools

    def get_tool_names(self) -> list[str]:
        """Get all available tool names from the MCP server."""
        if not self._tools:
            return []
        return [t.name for t in self._tools]


MAX_STARTUP_RETRIES = 5


def _agent_hostname(card_name: str) -> str:
    """Convert an agent card name to its Docker service hostname.
    Card names use underscores (venue_agent); Docker hostnames use hyphens (venue-agent).
    """
    return card_name.lower().replace("_", "-").replace(" ", "-")


class BaseConferenceAgent(A2AServer):
    """
    Base class for all conference agents.
    Handles: LLM client, MCP tool access, registry self-registration,
    and the autonomous tool-loop.

    Agents coordinate with peers via MCP tools (read_working_memory,
    write_working_memory, ask_agent, discover_agents) — not via
    hardcoded Python imports.
    """

    def __init__(self, agent_card, system_prompt: str, port: int):
        @asynccontextmanager
        async def _lifespan(app):
            await self._on_startup()
            yield
            await self._on_shutdown()

        super().__init__(agent_card, lifespan=_lifespan)
        self.system_prompt = system_prompt
        self.port = port
        self.llm = AsyncAzureOpenAI(
            azure_endpoint=config.azure_openai_endpoint,
            api_key=config.azure_openai_api_key,
            api_version=config.azure_openai_api_version
        )
        self._mcp = MCPConnection(config.mcp_server_url)

    async def _on_startup(self):
        # Connect to the MCP server with exponential-backoff retries
        for attempt in range(MAX_STARTUP_RETRIES):
            try:
                await self._mcp.connect()
                break
            except Exception as e:
                wait = 2 ** attempt
                print(f"[{self.card.name}] MCP connection attempt {attempt+1}/{MAX_STARTUP_RETRIES} "
                      f"failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
        else:
            raise RuntimeError(
                f"[{self.card.name}] FATAL: Could not connect to MCP server after "
                f"{MAX_STARTUP_RETRIES} attempts. Agent cannot function without tools."
            )

        # Register with the agent registry (retry until the registry is ready)
        hostname = _agent_hostname(self.card.name)
        agent_url = f"http://{hostname}:{self.port}"
        card_data = self.card.model_dump()
        for attempt in range(MAX_STARTUP_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(
                        f"{config.registry_url}/register",
                        json={"agent_url": agent_url, "card": card_data}
                    )
                    r.raise_for_status()
                print(f"[{self.card.name}] Registered at {agent_url}")
                break
            except Exception as e:
                wait = 2 ** attempt
                print(f"[{self.card.name}] Registry registration attempt {attempt+1}/{MAX_STARTUP_RETRIES} "
                      f"failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)

    async def _on_shutdown(self):
        await self._mcp.disconnect()

    # ─── LLM TOOL LOOP ───────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_assistant_message(msg) -> dict:
        """Build a clean assistant message dict for Azure OpenAI.

        ``msg.model_dump()`` can include ``None``-valued fields (e.g.
        ``refusal``, ``audio``, ``function_call``) that older Azure API
        versions reject with a 400 Bad Request.  This helper keeps only
        the fields Azure expects.
        """
        sanitized: dict = {"role": "assistant"}

        # content may be None when tool_calls are present; omit it in
        # that case so Azure doesn't see an explicit ``null``.
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

    # Delegate to module-level extract_json for backward compatibility
    _extract_json = staticmethod(extract_json)

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
                    f"[{self.card.name}] Rate-limited (429). "
                    f"Retrying in {delay}s (attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})…"
                )
                await asyncio.sleep(delay)
        # Unreachable: loop always returns or re-raises on final attempt

    async def llm_with_tools(self, task: Task, user_message: str) -> str:
        """
        Run the LLM in a tool-use loop.
        All tools come from MCP — including working memory, peer communication,
        web search, database queries, and vector search.

        The LLM autonomously decides which tools to call and when.
        Returns the LLM's final text response.
        """
        tools_schema = self._mcp.get_tools_schema()

        if not tools_schema:
            print(f"[{self.card.name}] WARNING: No tool schemas available.")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]

        max_iterations = 30
        for iteration in range(max_iterations):
            is_penultimate = iteration == max_iterations - 2

            response = await self._llm_create_with_retry(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            )

            msg = response.choices[0].message

            # If the LLM returned final text (no tool calls) → done
            if not msg.tool_calls:
                return self._extract_json(msg.content or "")

            # On the last iteration, force the LLM to produce a final answer
            # by dropping tools from the next call
            if is_penultimate:
                print(
                    f"[{self.card.name}] Approaching tool loop limit "
                    f"({max_iterations}). Next call will be without tools."
                )

            # LLM wants to call tools → execute them all concurrently via MCP
            messages.append(self._sanitize_assistant_message(msg))

            async def _exec_tool(tc):
                call_args = json.loads(tc.function.arguments)
                print(f"[{self.card.name}] 🛠️  Calling MCP tool '{tc.function.name}' with args: {tc.function.arguments}")
                try:
                    result = await self._mcp.call_tool(tc.function.name, call_args)
                except Exception as e:
                    print(
                        f"[{self.card.name}] ⚠️  Tool '{tc.function.name}' failed "
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
            f"[{self.card.name}] WARNING: LLM tool loop exhausted {max_iterations} "
            f"iterations without producing a final response. Returning partial summary."
        )
        return (
            f"[{self.card.name}] was unable to produce a final response within "
            f"{max_iterations} iterations. Please review partial results in working memory."
        )
