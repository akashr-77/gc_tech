import httpx
import json
from typing import Callable, Optional
from .models import TaskRequest, Task, TaskStatusUpdate, Message, TextPart, AgentCard

class A2AClient:
    """Client for sending tasks to an A2A agent and streaming responses."""

    def __init__(self, agent_url: str, timeout: int = 120):
        self.agent_url = agent_url.rstrip("/")
        self.timeout = timeout

    async def get_agent_card(self) -> AgentCard:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.agent_url}/.well-known/agent.json")
            r.raise_for_status()
            return AgentCard(**r.json())

    async def send_task(self, session_id: str, text: str,
                        metadata: Optional[dict] = None) -> str:
        """Send a task and return the task_id."""
        request = TaskRequest(
            session_id=session_id,
            message=Message(role="user", parts=[TextPart(text=text)]),
            metadata=metadata or {}
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.agent_url}/tasks",
                json=request.model_dump(mode="json")
            )
            r.raise_for_status()
            return r.json()["task_id"]

    async def stream_task(
        self,
        session_id: str,
        text: str,
        metadata: Optional[dict] = None,
        on_update: Optional[Callable[[TaskStatusUpdate], None]] = None
    ) -> Task:
        """Send a task and stream status updates until completion. Returns final Task."""
        task_id = await self.send_task(session_id, text, metadata)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "GET",
                f"{self.agent_url}/tasks/{task_id}/events"
            ) as response:
                final_task = None
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        update = TaskStatusUpdate(**data)
                        if on_update:
                            on_update(update)
                        if update.final:
                            # Fetch final task state
                            r = await client.get(
                                f"{self.agent_url}/tasks/{task_id}"
                            )
                            final_task = Task(**r.json())
                            break

                # If the remote agent reported a failure, raise so the
                # caller can distinguish crashes from empty results.
                if final_task and final_task.status == "failed":
                    # Try to extract an error message from the task
                    error_parts = []
                    for msg in final_task.messages:
                        if msg.role == "agent":
                            for part in msg.parts:
                                if hasattr(part, "text") and part.text:
                                    error_parts.append(part.text)
                    error_detail = "; ".join(error_parts) if error_parts else "unknown error"
                    raise RuntimeError(
                        f"Remote agent task {task_id} failed: {error_detail}"
                    )

                return final_task

    async def ask(self, session_id: str, question: str,
                  metadata: Optional[dict] = None) -> str:
        """Simple ask-and-wait. Returns the text response from the agent."""
        task = await self.stream_task(session_id, question, metadata)
        if task and task.artifacts:
            for part in task.artifacts[-1].parts:
                if hasattr(part, "text"):
                    return part.text
                if hasattr(part, "data"):
                    return json.dumps(part.data)
        return ""