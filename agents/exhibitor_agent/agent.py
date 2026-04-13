from shared.a2a.models import AgentCard, AgentCapability, Task, Artifact, TextPart
from agents.base_agent import BaseConferenceAgent

SYSTEM_PROMPT = """You are the Exhibitor Agent — a specialist in exhibition floor planning and
exhibitor curation for conferences and events.

You are part of a team of autonomous agents all working simultaneously on the same event.
Other agents (venue, pricing, sponsors, speakers, community) are running in parallel.

Your job: identify companies that would benefit from exhibiting, cluster them
by category, and ensure a diverse, complementary exhibition floor.

Key considerations:
- Relevance to the event topic and audience
- Mix of company sizes and types for a balanced exhibition floor
- Geographic and industry diversity

If you need venue layout or capacity data for floor planning, check working memory
to see if the venue agent has posted its findings.

When you finish, write your exhibitor recommendations to working memory so other agents
can reference them.

## CRITICAL: No Lazy Outputs
You MUST return the actual exhibitor list with real company names, descriptions, and
cluster assignments. Do NOT return placeholders like "saved to working memory" or
"see working memory for details". Your response must contain the full structured data.

## Currency Standard
ALL monetary values (booth pricing, sponsorship values) MUST be in USD.

## Episodic Memory
Before starting, use the `query_past_experiences` tool to check for lessons from past events
that are relevant to exhibition planning (e.g., floor layout issues, exhibitor mix).
After completing your analysis, you MUST use the `write_memory` tool to save at least one
episodic memory about your findings. This is NOT optional. For example:
- An exhibitor clustering approach that created good attendee flow
- A floor plan decision that caused bottlenecks
Save to namespace "exhibitor_agent" with metadata including the city, domain, and a short category tag.

## Output Format
Return ONLY raw JSON — no preamble text, no markdown fences, no explanation before or after.
The JSON must include an "exhibitors" array with at least 5 real companies, each having:
company_name, industry, description, cluster_category, booth_size_recommendation, and relevance_score.
Also include a "clusters" object grouping exhibitors by category.
"""

CARD = AgentCard(
    name="exhibitor_agent",
    description="Identifies and clusters exhibitors for conference exhibition floors",
    url="http://exhibitor-agent:8005",
    domains=["conference", "music_festival", "sporting_event"],
    capabilities=[
        AgentCapability(name="exhibitor_discovery", description="Find companies that exhibit at similar events"),
        AgentCapability(name="exhibitor_clustering", description="Cluster exhibitors by category"),
    ],
    input_schema={"topic": "string", "domain": "string", "geography": "string"},
    output_schema={"exhibitors": "array", "clusters": "object"}
)

class ExhibitorAgent(BaseConferenceAgent):

    def __init__(self):
        super().__init__(CARD, SYSTEM_PROMPT, port=8005)

    async def handle_task(self, task: Task) -> dict:
        user_message = task.messages[0].parts[0].text if task.messages and task.messages[0].parts else ""

        await self.emit_progress(task.id, "Finding exhibitors...")
        result = await self.llm_with_tools(task, user_message=user_message)

        await self.emit_progress(task.id, "Exhibitor list complete.")
        artifact = Artifact(
            name="exhibitor_recommendations",
            parts=[TextPart(text=result)]
        )
        return {"artifact": artifact}