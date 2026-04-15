# Intelligent AI Event Planner

An autonomous multi-agent system that plans conferences, festivals, and sporting events end-to-end. Given an event brief, the system dispatches specialist AI agents in parallel and combines their outputs into a complete plan covering venues, pricing, sponsors, speakers, exhibitors, and community distribution.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EventOps Agent :8000                         │
│  Orchestrator that discovers agents, broadcasts work in parallel,    │
│  and compiles the final event plan.                                  │
└──────────────┬───────────────────────────────────┬───────────────────┘
               │ A2A over SSE                      │ A2A over SSE
   ┌───────────▼───────────┐           ┌───────────▼───────────┐
   │ Venue / Pricing /     │           │ Sponsor / Speaker /   │
   │ Exhibitor / Community │           │ EventOps specialists  │
   └───────────┬───────────┘           └───────────┬───────────┘
               │                                   │
               └───────────────┬───────────────────┘
                               ▼
                  ┌───────────────────────────────┐
                  │ MCP Server :8080              │
                  │ Tool hub and SQL query layer  │
                  └───────────────┬───────────────┘
                                  ▼
                  ┌───────────────────────────────┐
                  │ PostgreSQL + pgvector :5432   │
                  │ memories, registry, events    │
                  │ working state, checkpoints    │
                  └───────────────────────────────┘
```

### Agents

| Agent | Port | Responsibility |
|-------|------|----------------|
| `eventops_agent` | 8000 | Orchestrator that combines all agent outputs |
| `venue_agent` | 8001 | Venue sourcing and evaluation |
| `pricing_agent` | 8002 | Ticket pricing strategy and attendance forecasting |
| `sponsor_agent` | 8003 | Sponsor discovery and proposal generation |
| `speaker_agent` | 8004 | Speaker discovery and agenda mapping |
| `exhibitor_agent` | 8005 | Exhibition floor planning and exhibitor curation |
| `community_agent` | 8006 | Community GTM strategy and distribution planning |

### Technical Overview

- **MCP server**: Exposes database queries, memory tools, web tools, and agent-to-agent helpers through a single SSE endpoint.
- **A2A protocol**: The agents communicate over streaming SSE so EventOps can fan out work and collect progress live.
- **PostgreSQL persistence**: The registry, working memory, procedural rules, checkpoint state, and event dataset all live in PostgreSQL.
- **SQL-backed event retrieval**: The event dataset is imported into the `events` table and queried with `ILIKE`, date filters, and full-text search instead of scanning the raw JSON file at runtime.
- **React frontend**: The UI in [frontend/](frontend/) is built with Vite and served on port 3000 in Docker Compose.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) v2
- An OpenAI-compatible LLM endpoint configured in [.env.example](.env.example)
- PostgreSQL credentials that match the connection string in `DATABASE_URL`

---

## Quick Start

### 1. Configure environment variables

git clone https://github.com/akashr-77/gc_tech
cd gc_tech

cp .env.example .env
# Edit .env and fill in your Azure OpenAI credentials and database password

### 2. Start the stack

```bash
docker compose up -d --build
```

This starts:
1. PostgreSQL with the schema mounted from [database/schema.sql](database/schema.sql)
2. The MCP server
3. The persistent agent registry
4. All specialist agents
5. The EventOps orchestrator
6. The React frontend on `http://localhost:3000`

Wait until `docker compose ps` shows the core services as healthy.

### 3. Import the event dataset

The planner now queries a SQL-backed `events` table. Import the dataset once after the stack is up:

```bash
docker compose run --rm --no-deps mcp-server python scripts/import_events.py
```

This reads [dataset/all_events_final.json](dataset/all_events_final.json), normalizes each record, truncates the `events` table, and upserts the rows with search support for name, category, country, location, date, and text search.

### 4. Run a sample planning session

```bash
python scripts/test_flow.py
```

You can also call the API directly:

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

Poll for results with the returned session id:

```bash
curl http://localhost:8000/sessions/<session_id>
```

### 5. Run tests

```bash
pytest
```

---

## API Reference

### EventOps Agent (`localhost:8000`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/plan` | Start a new event planning session |
| `GET` | `/sessions/{id}` | Get the current status and result of a session |
| `GET` | `/health` | Health check |

### Specialist Agents (`localhost:8001` to `8006`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/.well-known/agent.json` | Agent card with capabilities and schemas |
| `POST` | `/tasks` | Submit a task |
| `GET` | `/tasks/{id}` | Get task result |
| `GET` | `/tasks/{id}/events` | Stream task progress over SSE |
| `GET` | `/health` | Health check |

### Registry (`localhost:9000`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/agents` | List all registered agents |
| `GET` | `/agents/{name}` | Get one registered agent |
| `GET` | `/discover?capability=X&domain=Y` | Discover agents by capability or domain |
| `POST` | `/register` | Register an agent at startup |

### MCP Server (`localhost:8080`)

The MCP server exposes tools over SSE at `/sse`.

| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo search |
| `scrape_page` | Read webpages, including JS-rendered pages |
| `get_youtube_transcript` | Extract captions from YouTube videos |
| `read_rss_feed` | Read RSS or Atom feeds |
| `search_reddit` | Search public Reddit posts |
| `read_reddit_post` | Read a Reddit post and top comments |
| `search_github` | Search GitHub repositories |
| `read_github_repo` | Read a GitHub repository file |
| `vector_search` | Semantic search over agent memory |
| `write_memory` | Store episodic memory entries |
| `query_event_dataset` | Search the SQL-backed event table |
| `query_venues` | Query venue records |
| `query_sponsors` | Query sponsor records |
| `query_speakers` | Query speaker records |
| `query_communities` | Query community records |
| `get_pricing_benchmark` | Historical pricing benchmarks |
| `read_working_memory` | Read shared session state |
| `write_working_memory` | Write shared session state |
| `discover_agents` | Discover peer agents from the registry |
| `ask_agent` | Send work to a peer agent |
| `query_past_experiences` | Search past event memories |
| `query_guidelines_and_rules` | Fetch procedural rules and constraints |

---

## Environment Variables

See [.env.example](.env.example) for the full list. The most important variables are:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_KEY` | Yes | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | Yes | API version used by the clients |
| `AZURE_OPENAI_DEPLOYMENT` | Yes | Chat model deployment name |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Yes | Embedding deployment name |
| `POSTGRES_USER` | Yes | PostgreSQL user name |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password |
| `POSTGRES_DB` | Yes | PostgreSQL database name |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `MCP_SERVER_URL` | Yes | Internal MCP SSE URL used by the agents |
| `REGISTRY_URL` | Yes | Internal registry URL used by the agents |

---

## Data Pipeline

The dataset flow is:

1. The raw event feed lives in [dataset/all_events_final.json](dataset/all_events_final.json).
2. [scripts/import_events.py](scripts/import_events.py) normalizes each event and writes it into PostgreSQL.
3. [mcp_server/server.py](mcp_server/server.py) exposes `query_event_dataset`, which queries the `events` table with SQL filters.
4. EventOps uses that tool during planning to retrieve only the relevant rows.

To refresh the table after updating the JSON file, rerun:

```bash
docker compose run --rm --no-deps mcp-server python scripts/import_events.py
```

The database also stores:

- `agent_memories` for episodic memory
- `working_memory` for session-scoped context
- `procedural_rules` for business constraints
- `agent_tasks` for orchestration tracking
- `agent_registry` for persistent agent discovery

---

## Project Structure

```
newproj/
├── agents/
│   ├── base_agent.py
│   ├── community_agent/
│   ├── eventops_agent/
│   ├── exhibitor_agent/
│   ├── pricing_agent/
│   ├── speaker_agent/
│   ├── sponsor_agent/
│   └── venue_agent/
├── database/
│   ├── schema.sql
│   ├── 002_working_memory.sql
│   ├── 003_procedural_memory.sql
│   ├── 005_reactive_checkpoint.sql
│   └── 006_registry.sql
├── dataset/
│   └── all_events_final.json
├── frontend/
│   ├── Dockerfile
│   ├── index.html
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── index.css
│       ├── main.jsx
│       └── components/
│           ├── ChatSidebar.jsx
│           ├── PlanningForm.jsx
│           ├── ProgressView.jsx
│           ├── ResultsDashboard.jsx
│           ├── SessionHistory.jsx
│           └── ThinkingIndicator.jsx
├── mcp_server/
│   └── server.py
├── registry/
│   └── main.py
├── scripts/
│   ├── import_events.py
│   └── test_flow.py
├── shared/
│   ├── a2a/
│   ├── config.py
│   ├── event_dataset.py
│   └── memory/
├── tests/
├── docker-compose.yml
├── ENGINEERING.md
├── README.md
└── requirements.txt
```

---

## Domains Supported

- Conferences
- Music festivals
- Sporting events

The architecture is domain-agnostic. Domain-specific behavior comes from the prompts, the structured database records, and the procedural rules stored in PostgreSQL.
