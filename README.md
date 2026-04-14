# Manhattan Project — AI-Powered Conference Organizer

An autonomous multi-agent system that plans conferences, festivals, and sporting events end-to-end. Given an event topic, geography, budget, and target audience, the system dispatches specialist AI agents in parallel that collectively produce a complete event plan: venues, pricing, sponsors, speakers, exhibitors, and a go-to-market strategy.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      EventOps Agent  :8000                       │
│  (Orchestrator — discovers agents, broadcasts tasks in parallel, │
│   compiles all outputs into a unified final plan)                │
└─────────┬──────────────────────────────────────────┬────────────┘
          │  A2A Protocol (SSE streaming)             │
    ┌─────▼──────┐  ┌───────────┐  ┌──────────┐  ┌──▼──────────┐
    │VenueAgent  │  │PricingAgent│  │SponsorAgt│  │SpeakerAgent │
    │   :8001    │  │   :8002   │  │  :8003   │  │    :8004    │
    └─────┬──────┘  └─────┬─────┘  └────┬─────┘  └──────┬──────┘
          │               │             │                │
    ┌─────▼───────────────▼─────────────▼────────────────▼──────┐
    │              MCP Server  :8080  (Tool Hub)                  │
    │  web_search · scrape_page · vector_search · write_memory    │
    │  query_venues · query_sponsors · query_speakers             │
    │  read/write_working_memory · ask_agent · discover_agents    │
    │  query_past_experiences · query_guidelines_and_rules        │
    └──────────────────────┬─────────────────────────────────────┘
                           │
    ┌──────────────────────▼─────────────────────────────────────┐
    │              PostgreSQL + pgvector  :5432                   │
    │  agent_memories · working_memory · procedural_rules         │
    │  venues · sponsors · speakers · communities · pricing_models│
    │  orchestration_checkpoints · reactive_events · agent_registry│
    └────────────────────────────────────────────────────────────┘
```

### Agents

| Agent | Port | Responsibility |
|-------|------|----------------|
| `eventops_agent` | 8000 | Orchestrator — broadcasts all tasks, compiles final plan |
| `venue_agent` | 8001 | Venue sourcing and evaluation |
| `pricing_agent` | 8002 | Ticket pricing strategy and attendance forecasting |
| `sponsor_agent` | 8003 | Sponsor discovery and proposal generation |
| `speaker_agent` | 8004 | Speaker discovery and agenda mapping |
| `exhibitor_agent` | 8005 | Exhibition floor planning and exhibitor curation |
| `community_agent` | 8006 | Community GTM strategy and distribution plan |

### Key Design Decisions

- **MCP (Model Context Protocol):** All tools (DB queries, web search, vector search, agent communication) are exposed through a single MCP server, giving every agent a uniform tool interface without hardcoded dependencies.
- **A2A (Agent-to-Agent) Protocol:** Agents communicate via a streaming SSE protocol that supports parallel execution with live status updates.
- **Multi-tier Memory:**
  - *Episodic* — vector search over past event experiences (pgvector)
  - *Procedural* — hard business rules and compliance constraints (structured SQL)
  - *Working* — session-scoped blackboard for inter-agent context sharing
  - *Checkpoint* — crash-resilient orchestration state
- **Parallel Execution:** All specialist agents run simultaneously via `asyncio.gather`, then EventOps compiles their outputs in one final LLM call.
- **Persistent Registry:** Agent cards are stored in PostgreSQL, so registrations survive container restarts.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2.x)
- An **Azure OpenAI** resource with:
  - A GPT-4o deployment (or GPT-4-turbo)
  - A `text-embedding-3-large` deployment

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/amruth6002/manhattan-project.git
cd manhattan-project

cp .env.example .env
# Edit .env and fill in your Azure OpenAI credentials and database password
```

### 2. Start all services

```bash
docker compose up --build
```

This starts (in dependency order):
1. PostgreSQL with all schema migrations applied automatically
2. MCP Server (tool hub)
3. Agent Registry
4. All 6 specialist agents
5. EventOps orchestrator

Wait for all containers to show `healthy` status (~60–90 seconds on first run).

### 3. Run a test planning session

```bash
python scripts/test_flow.py
```

Or call the API directly:

```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Artificial Intelligence and Machine Learning",
    "domain": "conference",
    "city": "Bangalore",
    "country": "India",
    "budget_usd": 500000,
    "target_audience": 1000,
    "dates": "2026-09-15 to 2026-09-17"
  }'
```

Poll for results:
```bash
# Use the session_id from the response above
curl http://localhost:8000/sessions/<session_id>
```

---

## API Reference

### EventOps Agent (`localhost:8000`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/plan` | Start a new conference planning session |
| `GET` | `/sessions/{id}` | Get current status and results of a session |
| `GET` | `/health` | Health check |

### Any Specialist Agent (`localhost:8001–8006`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/.well-known/agent.json` | Agent card (capabilities, schemas) |
| `POST` | `/tasks` | Submit a task |
| `GET` | `/tasks/{id}` | Get task result |
| `GET` | `/tasks/{id}/events` | Stream task progress (SSE) |
| `GET` | `/health` | Health check |

### Registry (`localhost:9000`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/agents` | List all registered agents |
| `GET` | `/agents/{name}` | Get a specific agent |
| `GET` | `/discover?capability=X&domain=Y` | Discover agents by capability or domain |
| `POST` | `/register` | Register an agent (called automatically on startup) |

### MCP Server (`localhost:8080`)

The MCP server exposes tools via SSE at `/sse`. All web tools are **free and require no API keys**.

| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo search — no API key |
| `scrape_page` | Jina Reader — reads any webpage including JS-rendered sites |
| `get_youtube_transcript` | Extract captions from any YouTube video |
| `read_rss_feed` | Read any RSS/Atom feed |
| `search_reddit` | Search Reddit posts (public API) |
| `read_reddit_post` | Read a Reddit post and its top comments |
| `search_github` | Search GitHub repositories |
| `read_github_repo` | Read a GitHub repo's README or any file |
| `vector_search` | Semantic search over agent memory |
| `write_memory` | Store facts in episodic memory |
| `query_event_dataset` | Search the local JSON event database |
| `query_venues` | Query structured venue database |
| `query_sponsors` | Query sponsor database |
| `query_speakers` | Query speaker database |
| `query_communities` | Query community database |
| `get_pricing_benchmark` | Historical ticket pricing benchmarks |
| `read_working_memory` | Read the shared session blackboard |
| `write_working_memory` | Write to the shared session blackboard |
| `discover_agents` | Discover peer agents from the registry |
| `ask_agent` | Send a task to a peer agent |
| `query_past_experiences` | Search past event memories |
| `query_guidelines_and_rules` | Fetch business rules and compliance constraints |

---

## Environment Variables

See [`.env.example`](.env.example) for the complete list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | ✅ | Azure OpenAI resource URL |
| `AZURE_OPENAI_API_KEY` | ✅ | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | ✅ | GPT-4o deployment name |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | ✅ | Embedding model deployment name |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `POSTGRES_PASSWORD` | ✅ | PostgreSQL password (must match DATABASE_URL) |

---

## Data

The system seeds the database with:
- **Procedural rules** (`database/004_seed_memory.sql`): GDPR, medical compliance, budget guidelines, sponsorship policies, DEI requirements
- **Episodic memories** (`database/004_seed_memory.sql`): Lessons learned from past events (WiFi failures, pricing mistakes, channel strategy)
- **Reference dataset** (`dataset/all_events_final.json`): JSON event database used by the MCP server for similar-event lookups

To add more seed data to the vector store after startup, call the `write_memory` MCP tool or use the `vector_search` / `query_past_experiences` tools.

---

## Project Structure

```
manhattan-project/
├── agents/
│   ├── base_agent.py           # MCPConnection + BaseConferenceAgent
│   ├── eventops_agent/         # Orchestrator (port 8000)
│   ├── venue_agent/            # Venue specialist (port 8001)
│   ├── pricing_agent/          # Pricing specialist (port 8002)
│   ├── sponsor_agent/          # Sponsor specialist (port 8003)
│   ├── speaker_agent/          # Speaker specialist (port 8004)
│   ├── exhibitor_agent/        # Exhibitor specialist (port 8005)
│   └── community_agent/        # GTM specialist (port 8006)
├── database/
│   ├── schema.sql              # Core tables (venues, sponsors, speakers, etc.)
│   ├── 002_working_memory.sql  # Working memory blackboard
│   ├── 003_procedural_memory.sql # Business rules table
│   ├── 004_seed_memory.sql     # Seed rules + past experience memories
│   ├── 005_reactive_checkpoint.sql # Orchestration checkpoints + reactive events
│   └── 006_registry.sql        # Persistent agent registry
├── mcp_server/
│   └── server.py               # All MCP tools
├── registry/
│   └── main.py                 # Agent card registry (PostgreSQL-backed)
├── shared/
│   ├── a2a/                    # A2A protocol (models, server, client)
│   ├── memory/                 # Memory layer classes (episodic, procedural, working, checkpoint, reactive)
│   └── config.py               # Centralized configuration
├── scripts/
│   └── test_flow.py            # End-to-end test script
├── dataset/
│   └── all_events_final.json
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Domains Supported

- **Conferences** (tech, medical, finance, gaming)
- **Music Festivals**
- **Sporting Events**

The agent architecture is domain-agnostic — domain-specific logic is driven by the LLM system prompts and the procedural rules in the database.
