import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from .models import (
    Task, TaskRequest, TaskStatusUpdate, AgentCard,
    Message, TextPart
)

class A2AServer:
    """
    Base class for all A2A agent servers.
    Subclass this and implement `handle_task`.
    """

    def __init__(self, agent_card: AgentCard, lifespan=None):
        self.card = agent_card
        self.app = FastAPI(title=agent_card.name, lifespan=lifespan)
        self._tasks: dict[str, Task] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._setup_routes()    

    def _setup_routes(self):
        app = self.app

        @app.get("/.well-known/agent.json")
        async def get_agent_card():
            return self.card.model_dump()

        @app.get("/health")
        async def health():
            return {"status": "ok", "agent": self.card.name}

        @app.post("/tasks")
        async def create_task(request: TaskRequest):
            task = Task(
                session_id=request.session_id,
                messages=[request.message],
                metadata=request.metadata
            )
            self._tasks[task.id] = task
            self._queues[task.id] = asyncio.Queue()
            # Run handler in background
            asyncio.create_task(self._run_task(task))
            return {"task_id": task.id}

        @app.get("/tasks/{task_id}")
        async def get_task(task_id: str):
            task = self._tasks.get(task_id)
            if not task:
                from fastapi import HTTPException
                raise HTTPException(404, "Task not found")
            return task.model_dump(mode="json")

        @app.get("/tasks/{task_id}/events")
        async def stream_task_events(task_id: str):
            if task_id not in self._queues:
                from fastapi import HTTPException
                raise HTTPException(404, "Task not found")
            return StreamingResponse(
                self._event_generator(task_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
            )

    async def _event_generator(self, task_id: str) -> AsyncGenerator[str, None]:
        queue = self._queues[task_id]
        while True:
            update = await queue.get()
            yield f"data: {json.dumps(update.model_dump(mode='json'))}\n\n"
            if update.final:
                break

    async def _run_task(self, task: Task):
        task.status = "working"
        await self._emit(task.id, TaskStatusUpdate(
            task_id=task.id, status="working", final=False
        ))
        try:
            result = await self.handle_task(task)
            task.status = "completed"
            task.updated_at = datetime.now(timezone.utc)
            task.completed_at = datetime.now(timezone.utc)
            if result:
                task.artifacts.append(result["artifact"])
            await self._emit(task.id, TaskStatusUpdate(
                task_id=task.id,
                status="completed",
                artifact=task.artifacts[-1] if task.artifacts else None,
                final=True
            ))
        except Exception as e:
            task.status = "failed"
            task.updated_at = datetime.now(timezone.utc)
            await self._emit(task.id, TaskStatusUpdate(
                task_id=task.id,
                status="failed",
                message=Message(
                    role="agent",
                    parts=[TextPart(text=f"Error: {str(e)}")]
                ),
                final=True
            ))
            raise
        finally:
            # Clean up the queue after the task finishes to prevent memory leaks
            self._queues.pop(task.id, None)

    async def _emit(self, task_id: str, update: TaskStatusUpdate):
        if task_id in self._queues:
            await self._queues[task_id].put(update)

    async def emit_progress(self, task_id: str, message: str):
        """Call this from handle_task to stream intermediate updates."""
        await self._emit(task_id, TaskStatusUpdate(
            task_id=task_id,
            status="working",
            message=Message(role="agent", parts=[TextPart(text=message)]),
            final=False
        ))

    async def handle_task(self, task: Task) -> dict:
        """Override in subclass. Return {"artifact": Artifact}"""
        raise NotImplementedError