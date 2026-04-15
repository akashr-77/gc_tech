# Intelligent AI event planner

An autonomous multi-agent platform for planning conferences, festivals, and sports events end-to-end.  
Given event inputs (topic, domain, location, budget, dates, audience), the orchestrator delegates work to specialist agents and compiles a final plan.

---

## Architecture at a glance

- **EventOps orchestrator** (`:8000`) coordinates planning sessions
- **Specialist agents** (`:8001-8006`) handle venues, pricing, sponsors, speakers, exhibitors, and community GTM
- **MCP server** (`:8080`) exposes shared tools (web, social, dataset, memory, agent orchestration)
- **Registry** (`:9000`) tracks available agents
- **PostgreSQL + pgvector** (`:5432`) stores operational and memory data
- **Frontend** (`:3000`) provides the web UI

---

## Prerequisites

- Docker + Docker Compose v2
- Azure OpenAI credentials:
  - GPT deployment (for example `gpt-4o`)
  - Embedding deployment (for example `text-embedding-3-large`)

---

## Setup and run this repository

### 1) Clone this repo

```bash
git clone https://github.com/akashr-77/gc_tech.git
cd gc_tech
```

### 2) Configure environment variables

```bash
cp .env.example .env
```

Update `.env` values at minimum:
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `POSTGRES_PASSWORD` (and/or `DATABASE_URL`)

### 3) Start all services

```bash
docker compose up --build
```

This starts:
1. `postgres`
2. `mcp-server`
3. `registry`
4. Specialist agents (`venue/pricing/sponsor/speaker/exhibitor/community`)
5. `eventops-agent`
6. `frontend`

### 4) Load the event dataset (required once after startup)

```bash
docker compose run --rm --no-deps mcp-server python scripts/import_events.py
```

This imports `dataset/all_events_final.json` into the SQL-backed `events` table.

### 5) Use the app

- Frontend UI: `http://localhost:3000`
- EventOps API: `http://localhost:8000`
- MCP Server SSE: `http://localhost:8080/sse`
- Registry API: `http://localhost:9000`

### 6) Run a quick planning flow test (optional)

```bash
python scripts/test_flow.py
```

Or use API directly:

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

---

## Key APIs

### EventOps (`localhost:8000`)
- `POST /plan`
- `GET /sessions/{id}`
- `GET /health`

### Specialist agents (`localhost:8001-8006`)
- `GET /.well-known/agent.json`
- `POST /tasks`
- `GET /tasks/{id}`
- `GET /tasks/{id}/events`
- `GET /health`

### Registry (`localhost:9000`)
- `GET /agents`
- `GET /agents/{name}`
- `GET /discover?capability=X&domain=Y`
- `POST /register`

### MCP Server (`localhost:8080`)
- SSE endpoint: `GET /sse`
- Tools include web/social search, dataset querying, memory operations, and inter-agent orchestration utilities.

---

## Technical updates reflected in this repo

- Event discovery now uses a **SQL-backed events table** populated via `scripts/import_events.py`
- Docker stack includes a **frontend service** exposed at `localhost:3000`
- Persistent memory and orchestration state rely on PostgreSQL + pgvector schema in `database/`
- Agent discovery is centralized through the registry service

---

## Directory structure

```text
gc_tech/
├── agents/
│   ├── base_agent.py
│   ├── eventops_agent/
│   ├── venue_agent/
│   ├── pricing_agent/
│   ├── sponsor_agent/
│   ├── speaker_agent/
│   ├── exhibitor_agent/
│   └── community_agent/
├── database/
│   ├── schema.sql
│   ├── 002_working_memory.sql
│   ├── 003_procedural_memory.sql
│   ├── 005_reactive_checkpoint.sql
│   └── 006_registry.sql
├── dataset/
│   └── all_events_final.json
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   └── package.json
├── infra/
│   └── setup.sh
├── mcp_server/
│   ├── Dockerfile
│   └── server.py
├── registry/
│   ├── Dockerfile
│   └── main.py
├── scripts/
│   ├── import_events.py
│   └── test_flow.py
├── shared/
│   ├── a2a/
│   ├── memory/
│   ├── config.py
│   └── event_dataset.py
├── tests/
├── .env.example
├── docker-compose.yml
├── ENGINEERING.md
└── requirements.txt
```

---

## Supported domains

- Conferences
- Music festivals
- Sporting events
