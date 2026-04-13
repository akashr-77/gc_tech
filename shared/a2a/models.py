# Google A2A protocol data models
from pydantic import BaseModel, Field
from typing import Any, Optional, Literal
from datetime import datetime, timezone
import uuid

TaskStatus = Literal[
    "submitted", "working", "input_required",
    "completed", "failed", "canceled"
]

class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str
    mime_type: str = "text/plain"

class DataPart(BaseModel):
    type: Literal["data"] = "data"
    data: Any
    mime_type: str = "application/json"

class FilePart(BaseModel):
    type: Literal["file"] = "file"
    file_name: str
    file_content: str           # base64
    mime_type: str = "application/octet-stream"

Part = TextPart | DataPart | FilePart

class Message(BaseModel):
    role: Literal["user", "agent"]
    parts: list[Part]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Artifact(BaseModel):
    name: str
    parts: list[Part]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    status: TaskStatus = "submitted"
    messages: list[Message] = []
    artifacts: list[Artifact] = []
    metadata: dict = {}
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

class TaskRequest(BaseModel):
    session_id: str
    message: Message
    metadata: dict = {}

class TaskStatusUpdate(BaseModel):
    task_id: str
    status: TaskStatus
    message: Optional[Message] = None
    artifact: Optional[Artifact] = None
    confidence: float = 1.0
    final: bool = False

class AgentCapability(BaseModel):
    name: str
    description: str

class AgentCard(BaseModel):
    name: str
    description: str
    version: str = "1.0"
    url: str
    domains: list[str]           # ['conference', 'music_festival', 'sporting_event']
    capabilities: list[AgentCapability]
    input_schema: dict
    output_schema: dict
    authentication: dict = {"type": "none"}
    tags: list[str] = []

class EventInput(BaseModel):
    topic: str
    domain: str = "conference"
    city: str
    country: str
    budget_usd: int
    target_audience: int
    dates: str
    session_id: Optional[str] = None