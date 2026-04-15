import asyncio
import os
import json
import re
import httpx
from datetime import date as date_cls
from openai import AsyncAzureOpenAI
from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from shared.config import config

mcp = FastMCP("conference-tools", host="0.0.0.0", port=8080)

DATABASE_URL = config.database_url.replace("postgresql://", "postgresql+asyncpg://")
try:
    engine = create_async_engine(DATABASE_URL)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
except ModuleNotFoundError:
    engine = None
    session_factory = None
openai_client = AsyncAzureOpenAI(
    azure_endpoint=config.azure_openai_endpoint,
    api_key=config.azure_openai_api_key,
    api_version=config.azure_openai_api_version
)

# ─── WEB SEARCH ───────────────────────────────────────────────────────────────

@mcp.tool()
async def web_search(query: str, num_results: int = 10) -> list[dict]:
    """Search the web using DuckDuckGo. No API key required.
    Use for sponsors, speakers, venues, communities, and events."""
    from ddgs import DDGS

    def _search():
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))
        except Exception as e:
            raise RuntimeError(f"DuckDuckGo search failed: {str(e)}") from e

    results = await asyncio.to_thread(_search)
    return [
        {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
        for r in results
    ]

@mcp.tool()
async def scrape_page(url: str) -> str:
    """Scrape full text from any webpage via Jina Reader. No API key required.
    Handles JS-rendered pages, news sites, LinkedIn public profiles, and more."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            jina_url = f"https://r.jina.ai/{url}"
            r = await client.get(
                jina_url,
                headers={"User-Agent": "ConferenceAI/1.0", "Accept": "text/plain"},
                follow_redirects=True,
            )
            r.raise_for_status()
            return r.text
        except Exception:
            # Fallback: basic HTTP fetch
            try:
                r = await client.get(url, headers={"User-Agent": "ConferenceAI/1.0"})
                return r.text[:8000]
            except Exception as e:
                raise RuntimeError(f"Failed to scrape {url}: {str(e)}") from e

# ─── YOUTUBE ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_youtube_transcript(url: str, lang: str = "en") -> str:
    """Extract the full transcript from a YouTube video. No API key required.
    Works with videos that have captions (manual or auto-generated).
    Use for researching speaker talks, conference sessions, or industry keynotes."""
    from youtube_transcript_api import YouTubeTranscriptApi

    def _extract():
        match = re.search(r"(?:v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})", url)
        if not match:
            raise ValueError(f"Could not extract video ID from URL: {url}")
        video_id = match.group(1)
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
        except Exception as first_err:
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id)
            except Exception as e:
                return f"No transcript available for {url}: {str(first_err)}; fallback error: {str(e)}"
        return " ".join(item["text"] for item in transcript)

    return await asyncio.to_thread(_extract)

# ─── RSS ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def read_rss_feed(url: str, max_items: int = 20) -> dict:
    """Read any RSS or Atom feed and return the latest entries. No API key required.
    Use for conference news, speaker blogs, industry publications, and event calendars."""
    import feedparser

    def _parse():
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            exc = feed.get("bozo_exception", "unknown error")
            raise RuntimeError(f"Failed to parse RSS feed {url}: {exc}")
        return {
            "title": feed.feed.get("title", ""),
            "description": feed.feed.get("description", ""),
            "items": [
                {
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:500],
                    "published": entry.get("published", ""),
                }
                for entry in feed.entries[:max_items]
            ],
        }

    return await asyncio.to_thread(_parse)

# ─── REDDIT ───────────────────────────────────────────────────────────────────

@mcp.tool()
async def search_reddit(query: str, subreddit: str = None, limit: int = 10) -> list[dict]:
    """Search Reddit posts and threads. No API key required.
    Use for community opinions, real-world event feedback, and niche discussions."""
    params: dict = {"q": query, "limit": limit, "sort": "relevance", "t": "all"}
    if subreddit:
        search_url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params["restrict_sr"] = 1
    else:
        search_url = "https://www.reddit.com/search.json"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            search_url,
            params=params,
            headers={"User-Agent": "ConferenceResearcher/1.0"},
        )
        r.raise_for_status()
        posts = r.json().get("data", {}).get("children", [])
        return [
            {
                "title": p["data"].get("title"),
                "url": p["data"].get("url"),
                "score": p["data"].get("score"),
                "subreddit": p["data"].get("subreddit"),
                "permalink": "https://www.reddit.com" + p["data"].get("permalink", ""),
                "text": p["data"].get("selftext", "")[:500],
                "num_comments": p["data"].get("num_comments"),
            }
            for p in posts
        ]

@mcp.tool()
async def read_reddit_post(url: str) -> dict:
    """Read a Reddit post and its top comments in full. No API key required.
    Use for deep-dive community discussions about events, venues, or speakers."""
    clean = url.split("?")[0].rstrip("/")
    json_url = clean + ".json?limit=20"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            json_url,
            headers={"User-Agent": "ConferenceResearcher/1.0"},
            follow_redirects=True,
        )
        r.raise_for_status()
        data = r.json()
    post_data = data[0]["data"]["children"][0]["data"]
    comments_raw = data[1]["data"]["children"] if len(data) > 1 else []
    comments = [
        {
            "author": c["data"].get("author"),
            "text": c["data"].get("body", "")[:500],
            "score": c["data"].get("score"),
        }
        for c in comments_raw
        if c.get("kind") == "t1"
    ][:15]
    return {
        "title": post_data.get("title"),
        "author": post_data.get("author"),
        "subreddit": post_data.get("subreddit"),
        "score": post_data.get("score"),
        "text": post_data.get("selftext", ""),
        "url": post_data.get("url"),
        "num_comments": post_data.get("num_comments"),
        "comments": comments,
    }

# ─── GITHUB ───────────────────────────────────────────────────────────────────

@mcp.tool()
async def search_github(query: str, limit: int = 10) -> list[dict]:
    """Search GitHub repositories. No API key required (public rate limit: 60/hr).
    Use to research speakers' open-source projects or sponsors' tech stacks."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "per_page": limit, "sort": "stars"},
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "ConferenceAI/1.0"},
        )
        r.raise_for_status()
        return [
            {
                "name": item.get("full_name"),
                "description": item.get("description"),
                "stars": item.get("stargazers_count"),
                "language": item.get("language"),
                "url": item.get("html_url"),
                "topics": item.get("topics", []),
            }
            for item in r.json().get("items", [])
        ]

@mcp.tool()
async def read_github_repo(owner: str, repo: str, path: str = "") -> str:
    """Read a GitHub repository's README or any file. No API key required for public repos.
    Use to research speakers' projects, sponsors' products, or conference tooling."""
    api_path = f"contents/{path}" if path else "readme"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/{api_path}",
            headers={
                "Accept": "application/vnd.github.v3.raw",
                "User-Agent": "ConferenceAI/1.0",
            },
        )
        r.raise_for_status()
        return r.text[:10000]

# ─── VECTOR / EPISODIC MEMORY ─────────────────────────────────────────────────

@mcp.tool()
async def vector_search(query: str, namespace: str, limit: int = 10) -> list[dict]:
    """
    Semantic search in agent memory.
    namespace options: 'venue_agent', 'sponsor_agent', 'speaker_agent',
    'exhibitor_agent', 'pricing_agent', 'community_agent', 'seed_data'
    """
    resp = await openai_client.embeddings.create(
        model=config.azure_openai_embedding_deployment,
        input=[query],
        dimensions=config.embedding_dim
    )
    embedding = resp.data[0].embedding
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with session_factory() as session:
        result = await session.execute(text("""
            SELECT content, metadata, 1 - (embedding <=> CAST(:emb AS vector)) AS score
            FROM agent_memories
            WHERE namespace = :ns
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :limit
        """), {"ns": namespace, "emb": vec_str, "limit": limit})
        return [
            {"content": r[0], "metadata": r[1], "score": float(r[2])}
            for r in result.fetchall()
        ]

@mcp.tool()
async def write_memory(namespace: str, content: str, metadata: dict) -> bool:
    """Store a fact or result in the agent's episodic memory for future use."""
    resp = await openai_client.embeddings.create(
        model=config.azure_openai_embedding_deployment,
        input=[content],
        dimensions=config.embedding_dim
    )
    embedding = resp.data[0].embedding
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with session_factory() as session:
        await session.execute(text("""
            INSERT INTO agent_memories (namespace, content, embedding, metadata)
            VALUES (:ns, :content, CAST(:emb AS vector), CAST(:meta AS jsonb))
        """), {
            "ns": namespace, "content": content,
            "emb": vec_str, "meta": json.dumps(metadata)
        })
        await session.commit()
    return True

# ─── EPISODIC MEMORY (Past Experiences) ───────────────────────────────────────

@mcp.tool()
async def query_past_experiences(domain: str = None, city: str = None,
                                  query: str = None, limit: int = 5) -> list[dict]:
    """Search past event experiences — successes, mistakes, and lessons learned.
    Uses vector similarity search when a query is provided, otherwise filters by domain/city.
    Use this to avoid repeating past mistakes and to leverage proven strategies.

    Examples:
    - query_past_experiences(city="London") → what happened at past London events
    - query_past_experiences(domain="conference", query="WiFi issues") → find WiFi-related lessons
    - query_past_experiences(query="sponsorship strategy gaming") → search for relevant past learnings
    """
    # If a query is provided, use vector similarity search
    if query:
        resp = await openai_client.embeddings.create(
            model=config.azure_openai_embedding_deployment,
            input=[query],
            dimensions=config.embedding_dim
        )
        embedding = resp.data[0].embedding
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

        async with session_factory() as session:
            result = await session.execute(text("""
                SELECT content, metadata, 1 - (embedding <=> CAST(:emb AS vector)) AS score
                FROM agent_memories
                WHERE namespace = 'past_experiences'
                ORDER BY embedding <=> CAST(:emb AS vector)
                LIMIT :limit
            """), {"emb": vec_str, "limit": limit})
            return [
                {"content": r[0], "metadata": r[1], "relevance_score": float(r[2])}
                for r in result.fetchall()
            ]

    # Otherwise, filter by metadata fields (domain, city)
    filters = ["namespace = 'past_experiences'"]
    params: dict = {"limit": limit}
    if domain:
        filters.append("metadata->>'domain' ILIKE :domain")
        params["domain"] = f"%{domain}%"
    if city:
        filters.append("metadata->>'city' ILIKE :city")
        params["city"] = f"%{city}%"
    where = " AND ".join(filters)

    async with session_factory() as session:
        result = await session.execute(
            text(f"""
                SELECT content, metadata
                FROM agent_memories
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            params
        )
        return [
            {"content": r[0], "metadata": r[1]}
            for r in result.fetchall()
        ]


# ─── PROCEDURAL MEMORY (The Rulebook) ────────────────────────────────────────

@mcp.tool()
async def query_guidelines_and_rules(topic: str = None, region: str = None,
                                      domain: str = None) -> list[dict]:
    """Query business rules, compliance constraints, and SOPs that must be followed.
    Returns hard rules that should influence your recommendations.

    Topics include: 'gdpr', 'medical_compliance', 'budget', 'sponsorship',
    'speakers', 'venue_safety'

    Examples:
    - query_guidelines_and_rules(region="europe") → get all European regulations
    - query_guidelines_and_rules(topic="budget") → get budget allocation rules
    - query_guidelines_and_rules(topic="medical_compliance", region="us") → US healthcare rules
    - query_guidelines_and_rules(domain="music_festival") → festival-specific rules
    """
    filters = []
    params: dict = {}

    if topic:
        filters.append("topic ILIKE :topic")
        params["topic"] = f"%{topic}%"
    if region:
        filters.append("(region ILIKE :region OR region = 'global' OR region IS NULL)")
        params["region"] = f"%{region}%"
    if domain:
        filters.append("(domain ILIKE :domain OR domain IS NULL)")
        params["domain"] = f"%{domain}%"

    where = " AND ".join(filters) if filters else "TRUE"

    async with session_factory() as session:
        result = await session.execute(
            text(f"""
                SELECT topic, region, domain, rule_text, severity, source
                FROM procedural_rules
                WHERE {where}
                ORDER BY
                    CASE severity
                        WHEN 'critical' THEN 1
                        WHEN 'warning' THEN 2
                        WHEN 'info' THEN 3
                    END
            """),
            params
        )
        return [
            {
                "topic": r[0], "region": r[1], "domain": r[2],
                "rule": r[3], "severity": r[4], "source": r[5]
            }
            for r in result.fetchall()
        ]


# ─── DATABASE QUERIES ─────────────────────────────────────────────────────────

@mcp.tool()
async def query_venues(city: str, max_price_per_day: int = None,
                       min_capacity: int = None) -> list[dict]:
    """Query structured venue database by city, price, and capacity."""
    filters = ["LOWER(city) = LOWER(:city)"]
    params: dict = {"city": city}
    if max_price_per_day:
        filters.append("price_per_day <= :price")
        params["price"] = max_price_per_day
    if min_capacity:
        filters.append("capacity_max >= :cap")
        params["cap"] = min_capacity
    where = " AND ".join(filters)
    async with session_factory() as session:
        result = await session.execute(
            text(f"SELECT * FROM venues WHERE {where} ORDER BY price_per_day"),
            params
        )
        return [dict(r._mapping) for r in result.fetchall()]

@mcp.tool()
async def query_sponsors(industry: str = None, geography: str = None) -> list[dict]:
    """Query sponsor database with history of past sponsorships."""
    filters = []
    params: dict = {}
    if industry:
        filters.append("s.industry ILIKE :industry_like")
        params["industry_like"] = f"%{industry}%"
    where = " AND ".join(filters) if filters else "TRUE"
    async with session_factory() as session:
        result = await session.execute(text(f"""
            SELECT s.*, COUNT(sh.id) AS event_count,
                   MAX(sh.event_date) AS last_sponsored,
                   ARRAY_AGG(DISTINCT sh.event_domain) AS domains_sponsored
            FROM sponsors s
            LEFT JOIN sponsor_history sh ON sh.sponsor_id = s.id
            WHERE {where}
            GROUP BY s.id
            ORDER BY event_count DESC
        """), params)
        return [dict(r._mapping) for r in result.fetchall()]

@mcp.tool()
async def query_speakers(topic: str, geography: str = None) -> list[dict]:
    """Query speaker database by topic expertise."""
    async with session_factory() as session:
        result = await session.execute(text("""
            SELECT * FROM speakers
            WHERE :topic = ANY(topics) OR bio ILIKE :topic_like
            ORDER BY follower_count DESC NULLS LAST
            LIMIT 30
        """), {"topic": topic, "topic_like": f"%{topic}%"})
        return [dict(r._mapping) for r in result.fetchall()]

@mcp.tool()
async def query_communities(niche: str, platform: str = None,
                            geography: str = None) -> list[dict]:
    """Query community database for GTM targeting."""
    filters = ["niche ILIKE :niche"]
    params: dict = {"niche": f"%{niche}%"}
    if platform:
        filters.append("platform = :platform")
        params["platform"] = platform
    where = " AND ".join(filters)
    async with session_factory() as session:
        result = await session.execute(text(f"""
            SELECT * FROM communities
            WHERE {where}
            ORDER BY member_count DESC
        """), params)
        return [dict(r._mapping) for r in result.fetchall()]

@mcp.tool()
async def query_event_dataset(query: str = None, name: str = None,
                              category: str = None, country: str = None,
                              location: str = None, source: str = None,
                              date: str = None, limit: int = 20) -> list[dict]:
    """Query the SQL-backed events table with lexical filters and text search."""
    where_clauses = []
    params: dict = {}

    if query:
        where_clauses.append(
            "(" \
            "search_tsv @@ websearch_to_tsquery('english', :query) OR " \
            "name ILIKE :query_like OR description ILIKE :query_like OR " \
            "category ILIKE :query_like OR location ILIKE :query_like OR " \
            "country ILIKE :query_like OR source ILIKE :query_like" \
            ")"
        )
        params["query"] = query
        params["query_like"] = f"%{query}%"

    for column_name, value in (
        ("name", name),
        ("category", category),
        ("country", country),
        ("location", location),
        ("source", source),
    ):
        if value:
            where_clauses.append(f"{column_name} ILIKE :{column_name}")
            params[column_name] = f"%{value}%"

    if date:
        try:
            params["event_date"] = date_cls.fromisoformat(date)
        except ValueError:
            params["event_date"] = date
        where_clauses.append("event_date = :event_date")

    sql_parts = ["SELECT raw_event FROM events"]
    if where_clauses:
        sql_parts.append("WHERE " + " AND ".join(where_clauses))
    sql_parts.append("ORDER BY event_date DESC NULLS LAST, name ASC")
    if limit is not None and limit >= 0:
        sql_parts.append("LIMIT :limit")
        params["limit"] = limit

    async with session_factory() as session:
        result = await session.execute(text("\n".join(sql_parts)), params)
        return [row._mapping["raw_event"] for row in result.fetchall()]

@mcp.tool()
async def get_pricing_benchmark(domain: str, geography: str,
                                 audience_size: int) -> dict:
    """Get historical ticket pricing benchmarks for similar events."""
    async with session_factory() as session:
        result = await session.execute(text("""
            SELECT *, ABS(audience_size - :audience) AS size_diff
            FROM pricing_models
            WHERE event_domain = :domain
              AND (geography = :geo OR geography = 'global')
            ORDER BY size_diff ASC
            LIMIT 3
        """), {"domain": domain, "geo": geography, "audience": audience_size})
        rows = result.fetchall()
        if not rows:
            return {}
        # Average the closest 3
        models = [dict(r._mapping) for r in rows]
        return {
            "early_bird_avg": sum(m["early_bird_usd"] for m in models) // len(models),
            "regular_avg": sum(m["regular_usd"] for m in models) // len(models),
            "vip_avg": sum(m["vip_usd"] for m in models) // len(models),
            "conversion_avg": sum(m["conversion_rate"] for m in models) / len(models),
            "references": models
        }

# ─── SPONSORSHIP PROPOSAL GENERATION ──────────────────────────────────────────

@mcp.tool()
async def generate_proposal(
    sponsor_name: str,
    event_name: str,
    event_date: str,
    event_location: str,
    tier: str,
    amount_usd: int,
    benefits: list[str],
    audience_size: int,
    event_domain: str,
    past_collaborations: list[str] | None = None,
    contact_name: str | None = None,
) -> str:
    """Generate a personalized sponsorship proposal document in Markdown.

    Creates a professional proposal with the sponsor's name, event details,
    tier benefits, pricing, and past collaboration history. Can be used for
    email outreach or converted to PDF.

    Args:
        sponsor_name: Company name of the prospective sponsor.
        event_name: Name/title of the event.
        event_date: Date(s) of the event (e.g. "June 15-17, 2026").
        event_location: City and venue of the event.
        tier: Sponsorship tier (e.g. "Platinum", "Gold", "Silver").
        amount_usd: Sponsorship investment amount in USD.
        benefits: List of benefits for this tier.
        audience_size: Expected number of attendees.
        event_domain: Domain of the event (e.g. "conference", "music_festival").
        past_collaborations: Optional list of past events where the sponsor participated.
        contact_name: Optional name of the contact person at the sponsor company.
    Returns:
        A Markdown-formatted sponsorship proposal document.
    """
    benefits_md = "\n".join(f"- {b}" for b in benefits)

    collab_section = ""
    if past_collaborations:
        collab_items = "\n".join(f"- {c}" for c in past_collaborations)
        collab_section = (
            f"\n## Our Shared History\n\n"
            f"We value our ongoing relationship with {sponsor_name}. "
            f"Previous collaborations include:\n\n{collab_items}\n\n"
            f"We look forward to building on this successful partnership.\n"
        )

    greeting = f"Dear {contact_name}," if contact_name else f"Dear {sponsor_name} Team,"

    proposal = f"""# Sponsorship Proposal: {event_name}

**Prepared exclusively for {sponsor_name}**

---

{greeting}

We are delighted to invite **{sponsor_name}** to partner with us as a **{tier} Sponsor** for **{event_name}**.

## Event Overview

| Detail | Information |
|--------|-------------|
| **Event** | {event_name} |
| **Domain** | {event_domain.replace("_", " ").title()} |
| **Date** | {event_date} |
| **Location** | {event_location} |
| **Expected Audience** | {audience_size:,} attendees |

## {tier} Sponsorship Package — ${amount_usd:,} USD

### Benefits Included

{benefits_md}
{collab_section}
## Why Partner With Us?

- **Targeted Reach**: Direct access to {audience_size:,} engaged professionals in the {event_domain.replace("_", " ")} space.
- **Brand Visibility**: Premium placement across all event materials, signage, and digital channels.
- **Thought Leadership**: Opportunity to showcase {sponsor_name}'s expertise and innovations.
- **Networking**: Exclusive access to speakers, VIPs, and industry leaders.

## Next Steps

1. Review the {tier} package details above.
2. Let us know if you'd like to customize any benefits.
3. Confirm your sponsorship to secure your {tier} placement.

We would be thrilled to have {sponsor_name} as a {tier} sponsor and look forward to creating a mutually rewarding partnership.

---

*This proposal was generated for {sponsor_name} | {event_name} | {event_date}*
"""
    return proposal


# ─── SCHEDULE BUILDER WITH CONFLICT DETECTION ────────────────────────────────

@mcp.tool()
async def build_schedule(
    sessions: list[dict],
    rooms: list[str],
    time_slots: list[str],
) -> dict:
    """Build a conflict-free event schedule from speaker-topic mappings, rooms, and time slots.

    Takes a list of session objects (each with a speaker, topic, and optional
    duration/priority) plus available rooms and time slots, and produces a
    time-slotted schedule grid. Detects and reports conflicts such as:
    - Same speaker assigned to two sessions in the same time slot
    - Room double-booked in the same time slot
    - More sessions than available room×slot capacity

    Args:
        sessions: List of dicts, each with keys:
            - "speaker" (str): Speaker name.
            - "topic" (str): Session/talk title.
            - "duration_slots" (int, optional): Number of consecutive slots needed (default 1).
            - "preferred_room" (str, optional): Preferred room, if any.
        rooms: List of available room names (e.g. ["Main Hall", "Room A", "Room B"]).
        time_slots: List of time slot labels in chronological order
            (e.g. ["09:00-10:00", "10:00-11:00", "11:00-12:00"]).

    Returns:
        A dict with:
        - "schedule": list of assigned sessions with slot, room, speaker, topic.
        - "conflicts": list of any detected conflicts (empty if conflict-free).
        - "unassigned": list of sessions that could not be placed.
    """
    total_capacity = len(rooms) * len(time_slots)

    # Grid tracking: (slot_index, room) -> assigned session
    grid: dict[tuple[int, str], dict] = {}
    # Track speaker assignments: speaker -> set of occupied slot indices
    speaker_slots: dict[str, set[int]] = {}

    assigned: list[dict] = []
    conflicts: list[str] = []
    unassigned: list[dict] = []

    if len(sessions) > total_capacity:
        conflicts.append(
            f"Capacity exceeded: {len(sessions)} sessions but only "
            f"{total_capacity} room-slot combinations available "
            f"({len(rooms)} rooms × {len(time_slots)} slots)."
        )

    for sess in sessions:
        speaker = sess.get("speaker", "TBD")
        topic = sess.get("topic", "Untitled")
        duration = sess.get("duration_slots", 1)
        preferred_room = sess.get("preferred_room")

        placed = False

        # Try preferred room first, then others
        room_order = list(rooms)
        if preferred_room and preferred_room in rooms:
            room_order = [preferred_room] + [r for r in rooms if r != preferred_room]

        for room in room_order:
            for slot_idx in range(len(time_slots) - duration + 1):
                # Check if all needed consecutive slots are free
                slots_needed = list(range(slot_idx, slot_idx + duration))
                room_free = all(
                    (si, room) not in grid for si in slots_needed
                )
                speaker_free = all(
                    si not in speaker_slots.get(speaker, set())
                    for si in slots_needed
                )

                if room_free and speaker_free:
                    # Place the session
                    for si in slots_needed:
                        grid[(si, room)] = {
                            "speaker": speaker,
                            "topic": topic,
                        }
                        speaker_slots.setdefault(speaker, set()).add(si)

                    time_label = time_slots[slot_idx]
                    if duration > 1:
                        end_slot = time_slots[slot_idx + duration - 1]
                        time_label = f"{time_slots[slot_idx]} to {end_slot}"

                    assigned.append({
                        "time_slot": time_label,
                        "room": room,
                        "speaker": speaker,
                        "topic": topic,
                    })
                    placed = True
                    break
            if placed:
                break

        if not placed:
            unassigned.append({"speaker": speaker, "topic": topic})
            # Diagnose why
            speaker_occupied = speaker_slots.get(speaker, set())
            if speaker_occupied:
                occupied_labels = [time_slots[i] for i in sorted(speaker_occupied)
                                   if i < len(time_slots)]
                conflicts.append(
                    f"Speaker conflict: '{speaker}' is already scheduled in "
                    f"slot(s) {occupied_labels} and no free room+slot "
                    f"combination remains for '{topic}'."
                )
            else:
                conflicts.append(
                    f"No available room-slot for session '{topic}' "
                    f"by '{speaker}'."
                )

    # Build the schedule grid for display
    schedule_grid: list[dict] = []
    for slot_idx, slot_label in enumerate(time_slots):
        row: dict = {"time_slot": slot_label}
        for room in rooms:
            cell = grid.get((slot_idx, room))
            if cell:
                row[room] = f"{cell['topic']} ({cell['speaker']})"
            else:
                row[room] = ""
        schedule_grid.append(row)

    return {
        "schedule": assigned,
        "schedule_grid": schedule_grid,
        "conflicts": conflicts,
        "unassigned": unassigned,
        "summary": {
            "total_sessions": len(sessions),
            "assigned": len(assigned),
            "unassigned": len(unassigned),
            "conflicts_detected": len(conflicts),
        },
    }


# ─── WORKING MEMORY (shared blackboard) ───────────────────────────────────────

@mcp.tool()
async def read_working_memory(session_id: str, agent_name: str = None,
                               key: str = None) -> list[dict]:
    """Read from the shared working memory blackboard.
    - read_working_memory(session_id) → all context from all agents for this session
    - read_working_memory(session_id, agent_name) → all context from one specific agent
    - read_working_memory(session_id, agent_name, key) → one specific value
    Use this to check what other agents have figured out so far."""
    filters = ["session_id = :sid"]
    params: dict = {"sid": session_id}
    if agent_name:
        filters.append("agent_name = :agent")
        params["agent"] = agent_name
    if key:
        filters.append("key = :key")
        params["key"] = key
    where = " AND ".join(filters)

    async with session_factory() as session:
        result = await session.execute(
            text(f"""
                SELECT agent_name, key, value, updated_at
                FROM working_memory
                WHERE {where}
                ORDER BY updated_at DESC
            """),
            params
        )
        rows = result.fetchall()
        return [
            {
                "agent": r[0], "key": r[1], "value": r[2],
                "updated_at": r[3].isoformat() if r[3] else None
            }
            for r in rows
        ]


@mcp.tool()
async def write_working_memory(session_id: str, agent_name: str,
                                key: str, value: str) -> bool:
    """Write a result or finding to the shared working memory blackboard.
    Other agents can read this using read_working_memory.
    Use this to share your findings (e.g., venue shortlist, pricing model) with peer agents."""
    async with session_factory() as session:
        await session.execute(text("""
            INSERT INTO working_memory (session_id, agent_name, key, value)
            VALUES (:sid, :agent, :key, CAST(:value AS jsonb))
            ON CONFLICT (session_id, agent_name, key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """), {
            "sid": session_id, "agent": agent_name,
            "key": key, "value": json.dumps(value)
        })
        await session.commit()
    return True


# ─── AGENT-TO-AGENT COMMUNICATION ─────────────────────────────────────────────

REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:9000")

@mcp.tool()
async def discover_agents(capability: str = None, domain: str = None) -> list[dict]:
    """Discover available peer agents and their capabilities from the registry.
    Use this to find which specialist agents exist and what they can do.
    Returns a list of agents with their names, descriptions, and capabilities."""
    params = {}
    if capability:
        params["capability"] = capability
    if domain:
        params["domain"] = domain

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{REGISTRY_URL}/discover", params=params)
        r.raise_for_status()
        agents = r.json()

    return [
        {
            "name": entry.get("card", {}).get("name"),
            "description": entry.get("card", {}).get("description"),
            "capabilities": [
                c.get("name") + ": " + c.get("description", "")
                for c in entry.get("card", {}).get("capabilities", [])
            ],
            "domains": entry.get("card", {}).get("domains", [])
        }
        for entry in agents
    ]

@mcp.tool()
async def ask_agent(agent_name: str, question: str, session_id: str) -> str:
    """Send a question to a peer agent and get their response.
    Use discover_agents first to find the right agent.
    The peer agent will use its own tools and reasoning to answer."""
    # Resolve agent URL from registry
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{REGISTRY_URL}/agents/{agent_name}")
        r.raise_for_status()
        agent_url = r.json().get("url")

    if not agent_url:
        return json.dumps({"error": f"Agent '{agent_name}' not found in registry"})

    # Send task via A2A protocol
    async with httpx.AsyncClient(timeout=180) as client:
        # Create task
        task_req = {
            "session_id": session_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": question}]
            }
        }
        r = await client.post(f"{agent_url}/tasks", json=task_req)
        r.raise_for_status()
        task_id = r.json()["task_id"]

        # Stream events until final
        async with client.stream("GET", f"{agent_url}/tasks/{task_id}/events") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("final"):
                        # Fetch final task
                        r2 = await client.get(f"{agent_url}/tasks/{task_id}")
                        task_data = r2.json()
                        # Extract result from artifact
                        for artifact in task_data.get("artifacts", []):
                            for part in artifact.get("parts", []):
                                if part.get("type") == "text":
                                    return part["text"]
                                if part.get("type") == "data":
                                    return json.dumps(part["data"])
                        return json.dumps(task_data)

    return json.dumps({"error": "No response received from agent"})

if __name__ == "__main__":
    mcp.run(transport="sse")