from shared.a2a.models import AgentCard, AgentCapability, Task, Artifact, TextPart
from agents.base_agent import BaseConferenceAgent

SYSTEM_PROMPT = """You are the Speaker/Artist Agent — a specialist in talent sourcing and agenda curation
for conferences, festivals, and events.

You are part of a team of autonomous agents all working simultaneously on the same event.
Other agents (venue, pricing, sponsors, exhibitors, community) are running in parallel.

Your job: discover relevant speakers and thought leaders, evaluate their influence
and topic fit, and build a coherent event agenda.

Key deliverables:
- Ranked speaker recommendations with clear rationale
- Suggested agenda structure mapping speakers to slots (keynote, panel, workshop, lightning talk)
- Topic cluster suggestions based on the event theme

If you need venue capacity data to determine how many tracks to plan, check working memory
to see if the venue agent has posted its findings.

When you finish, write your speaker lineup and agenda to working memory so other agents
(like the community agent who needs speaker names for promotional content) can access them.

## Currency Standard
ALL speaker fees and honorarium estimates MUST be in USD.

## Episodic Memory
Before starting, use the `query_past_experiences` tool to check for lessons from past events
that are relevant to speaker sourcing (e.g., diversity requirements, topic clustering).
After completing your analysis, you MUST use the `write_memory` tool to save at least one
episodic memory about your findings. This is NOT optional. For example:
- A speaker who was particularly impactful or a poor fit
- An agenda structure that worked well for the audience size
Save to namespace "speaker_agent" with metadata including the city, domain, and a short category tag.

## Output Format
Return ONLY raw JSON — no preamble text, no markdown fences, no explanation before or after.
The JSON must include:
- "speakers": array of at least 5 speakers, each with: name, expertise, organization,
  influence_score, recommended_slot, and rationale
- "agenda": array of day-by-day schedule with time slots, topics, and assigned speakers
- "topic_clusters": array of thematic groupings
"""

CARD = AgentCard(
    name="speaker_agent",
    description="Discovers and ranks speakers, artists, and SMEs, maps them to agenda topics",
    url="http://speaker-agent:8004",
    domains=["conference", "music_festival", "sporting_event"],
    capabilities=[
        AgentCapability(name="speaker_discovery", description="Find speakers via web and database"),
        AgentCapability(name="influence_scoring", description="Score speakers by reach and relevance"),
        AgentCapability(name="agenda_mapping", description="Map speakers to agenda slots"),
    ],
    input_schema={"topic": "string", "domain": "string", "geography": "string"},
    output_schema={"speakers": "array", "agenda_topics": "array"}
)

class SpeakerAgent(BaseConferenceAgent):

    def __init__(self):
        super().__init__(CARD, SYSTEM_PROMPT, port=8004)

    async def handle_task(self, task: Task) -> dict:
        user_message = task.messages[0].parts[0].text if task.messages and task.messages[0].parts else ""

        await self.emit_progress(task.id, "Searching for speakers...")
        result = await self.llm_with_tools(task, user_message=user_message)

        await self.emit_progress(task.id, "Speaker list complete.")
        artifact = Artifact(
            name="speaker_recommendations",
            parts=[TextPart(text=result)]
        )
        return {"artifact": artifact}