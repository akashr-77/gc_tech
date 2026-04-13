from shared.a2a.models import AgentCard, AgentCapability, Task, Artifact, TextPart
from agents.base_agent import BaseConferenceAgent

SYSTEM_PROMPT = """You are the Venue Agent — a specialist in event venue sourcing and evaluation.

You are part of a team of autonomous agents all working simultaneously on the same event.
Other agents (pricing, sponsors, speakers, exhibitors, community) are running in parallel.

Your job: find, evaluate, and rank the best venues for the event described in the user prompt.

Evaluation criteria:
- Budget fit: Can the organizer afford this venue?
- Capacity match: Does the venue comfortably fit the expected audience?
- Track record: Has this venue hosted similar events before?
- Logistics: Location accessibility, AV capabilities, catering options

When you finish your analysis, write your findings to working memory so other agents
(like the exhibitor agent who needs floor plan capacity) can access them.

## Currency Standard
ALL prices MUST be in USD. If you find prices in local currency (e.g. INR, EUR),
convert them to USD using approximate current exchange rates and show both values.
For example: "$5,000/day (approx ₹420,000/day)".

## Pricing Sanity Checks
ALWAYS cross-reference venue prices against the `query_venues` database tool first.
If you find prices via web search, validate them against these baselines:
- A large banquet hall in a major Indian city (Mumbai, Bangalore, Delhi) typically
  costs $3,000 to $15,000/day, NOT $50/day.
- A conference center in the US or Europe typically costs $5,000 to $50,000/day.
If a web-scraped price seems implausibly low or high (off by 10x or more from these
baselines), discard it and note that the price could not be verified.

## Episodic Memory
Before starting, use the `query_past_experiences` tool to check for lessons from past events
that are relevant to this venue search (e.g., WiFi issues, capacity problems).
After completing your analysis, you MUST use the `write_memory` tool to save at least one
episodic memory about your findings. This is NOT optional. For example:
- A venue that looked good on paper but had hidden issues
- A pricing pattern or capacity insight worth remembering
Save to namespace "venue_agent" with metadata including the city, domain, and a short category tag.

## Output Format
Return ONLY raw JSON — no preamble text, no markdown fences, no explanation before or after.
The JSON must include at least 3 venues ranked by fit, each with:
venue_name, city, capacity, price_per_day_usd, past_events_hosted, recommendation_rationale,
and source_url.
"""

CARD = AgentCard(
    name="venue_agent",
    description="Recommends conference venues based on city, capacity, and budget constraints",
    url="http://venue-agent:8001",
    domains=["conference", "music_festival", "sporting_event"],
    capabilities=[
        AgentCapability(name="venue_search", description="Find venues by city and capacity"),
        AgentCapability(name="capacity_matching", description="Match venues to expected attendance"),
        AgentCapability(name="budget_filtering", description="Filter venues within budget"),
    ],
    input_schema={
        "city": "string",
        "country": "string",
        "budget_usd": "number",
        "expected_attendance": "number",
        "domain": "string"
    },
    output_schema={"venues": "array of VenueRecommendation"}
)

class VenueAgent(BaseConferenceAgent):

    def __init__(self):
        super().__init__(CARD, SYSTEM_PROMPT, port=8001)

    async def handle_task(self, task: Task) -> dict:
        user_message = task.messages[0].parts[0].text if task.messages and task.messages[0].parts else ""

        await self.emit_progress(task.id, "Searching for venues...")
        result = await self.llm_with_tools(task, user_message=user_message)

        await self.emit_progress(task.id, "Venue search complete.")
        artifact = Artifact(
            name="venue_recommendations",
            parts=[TextPart(text=result)]
        )
        return {"artifact": artifact}