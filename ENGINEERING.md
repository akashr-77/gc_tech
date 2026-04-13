# Manhattan Project: Engineering Design Document

## 1. Executive Summary
The **Manhattan Project** is a decentralized, multi-agent AI system designed to autonomously orchestrate end-to-end event planning (conferences, music festivals, sporting events). 
Instead of relying on a single monolithic LLM, the architecture implements a **Swarm/Multi-Agent approach** where a central orchestrator delegates highly specific tasks to parallelized "Specialist Agents". All agents interface with external data sources securely via a centralized Model Context Protocol (MCP) server.

## 2. Core Architecture

The system is built on a microservices architecture entirely containerized via Docker.

### 2.1 Agent-to-Agent (A2A) Protocol
All agents communicate using a standardized A2A protocol over Server-Sent Events (SSE). 
*   **Decoupling:** Agents are completely decoupled from each other. They interact strictly through `TaskRequest` and `TaskStatusUpdate` Pydantic models via HTTP endpoints (`/tasks`, `/tasks/{id}/events`).
*   **State Machine:** Every task flows through a strict state machine: `submitted` -> `working` -> `completed` / `failed` / `input_required`.
*   **Parallelism:** The protocol enables horizontal scaling, allowing the orchestrator to fire parallel requests to the Venue, Pricing, and Speaker agents simultaneously.

### 2.2 Model Context Protocol (MCP) Server
Instead of giving each agent direct internet access or duplicate database connections, all external interactions are centralized in the **MCP Server** (`port 8080`).
*   **Uniform Tooling:** Exposes tools for web search (DuckDuckGo), website scraping (Jina Reader), GitHub/Reddit reading, and SQL/vector database queries.
*   **Zero-Latent Integration:** Agents hit the `.well-known/agent.json` or MCP endpoints to immediately inherit these capabilities without locally importing the underlying dependencies.

---

## 3. Component Breakdown

### 3.1 EventOps Orchestrator (`port 8000`)
The central node of the swarm. It receives user inputs (`POST /plan`), queries the **Registry** to discover online specialist agents, and partitions the event planning process into agent-specific sub-goals.
*   **Session Management:** Monitors the streaming status of all dispatched tasks.
*   **Checkpoint Persistence:** Employs the `CheckpointStore` to persist the orchestration state to PostgreSQL. If the container crashes mid-planning, `_on_startup()` automatically resumes incomplete sessions.

### 3.2 Specialist Agents (`ports 8001-8006`)
*   **`venue_agent`**: Queries the `venues` table and scrapes properties to match budget and capacity requirements.
*   **`pricing_agent`**: Looks at historical models and forecasts ticket attendance and conversion rates.
*   **`sponsor_agent`**: Queries `sponsor_history` to dynamically match high-budget corporations with the event domain.
*   **`speaker_agent`**: Curates industry-specific speakers based on semantic social media reach.
*   **`exhibitor_agent`**: Organizes floor layout logic.
*   **`community_agent`**: Generates multi-platform Go-To-Market and grass-roots growth strategies.

### 3.3 Dynamic Agent Registry (`port 9000`)
A microservice tracking online instances. Upon boot, every agent registers an `AgentCard` outlining its domain expertise and API schemas. The Orchestrator queries this registry rather than maintaining hardcoded IP addresses.

---

## 4. Persistent Storage (PostgreSQL & pgvector)

The repository heavily relies on structured schemas (`database/`) for long-term agent memory.

### 4.1 Memory Subsystems
1.  **Episodic Memory (`agent_memories`)**: Uses PostgreSQL `pgvector` (`1536` dimensions) to store "Lessons Learned" from past events. Agents perform nearest-neighbor semantic search to avoid repeating past logistical mistakes.
2.  **Procedural Memory (`procedural_rules`)**: Hardcoded business compliance logic (e.g., GDPR mandates, venue safety regulations, diversity quotas).
3.  **Working Memory (`working_memory`)**: A transient key-value blackboard where agents share live context across the same session (e.g. the venue agent writing the finalized location so the pricing agent knows local currency constraints).
4.  **Reactive Checkpoints (`orchestration_checkpoints`, `reactive_events`)**: Crash resilience module mapping the exact orchestrator trajectory.

### 4.2 Relational Domain Tables
The application queries production data models rather than relying blindly on LLM hallucinations:
*   `venues`, `sponsors`, `sponsor_history`, `speakers`, `communities`, `pricing_models`

---

## 5. Deployment Lifecycle

### Docker Network
*   Built efficiently via Python 3.11-slim base images.
*   `docker-compose.yml` ensures hard boot order via Healthchecks: `postgres` must validate before `registry`, which validates before `mcp-server`, finally booting the specific `agents`.
*   Data volumes (`pgdata`) persist all vector embeddings and registry instances locally.

### CI/CD Hygiene
The project operates under a strict `.gitignore` policy, guaranteeing datasets and environment credentials (`.env`) are never pushed, preserving cloud security for Azure OpenAI integration.
