from shared.a2a.models import AgentCard, AgentCapability, Task, Artifact, TextPart
from agents.base_agent import BaseConferenceAgent

SYSTEM_PROMPT = """You are the Pricing & Footfall Agent — a specialist in event ticket pricing strategy
and attendance forecasting.

You are part of a team of autonomous agents all working simultaneously on the same event.
Other agents (venue, sponsors, speakers, exhibitors, community) are running in parallel.

Your job: build a data-driven pricing model and forecast attendance for the event.

Key deliverables:
- Multi-tier ticket pricing (early bird, regular, VIP) with clear rationale
- Attendance forecast with low/expected/high range
- Revenue projection with break-even analysis
- Conversion funnel assumptions

Consider geography-based pricing differences (e.g., India vs US markets) and always ground
your recommendations in real data where possible.

If you need venue cost data to calculate break-even, check working memory to see if the
venue agent has posted its findings. If not available yet, make reasonable assumptions
and note them explicitly.

When you finish, write your pricing model to working memory so other agents
(like the sponsor agent who needs revenue projections) can access them.

## Currency Standard
ALL prices MUST be in USD as the primary currency. If the event is in a non-US location,
also show the local currency equivalent in parentheses. For example:
"$90 USD (approx ₹7,500 INR)".
The revenue_forecast and all tier prices in your output JSON must use USD numeric values.

## Episodic Memory
Before starting, use the `query_past_experiences` tool to check for lessons from past events
that are relevant to pricing (e.g., pricing mistakes, conversion insights).
After completing your analysis, you MUST use the `write_memory` tool to save at least one
episodic memory about your findings. This is NOT optional. For example:
- A pricing strategy that worked well or poorly for a specific geography
- An unexpected conversion rate pattern
Save to namespace "pricing_agent" with metadata including the city, domain, and a short category tag.

## Output Format
Return ONLY raw JSON — no preamble text, no markdown fences, no explanation before or after.
The JSON must include:
- "pricing_tiers": array with early_bird, regular, and vip tiers, each having:
  tier_name, price_usd, local_price_equivalent, quantity, and rationale
- "revenue_forecast_usd": total projected revenue in USD
- "attendance_forecast": object with low, expected, and high estimates
- "break_even_analysis": object with fixed_costs_usd, variable_costs_usd, and break_even_attendees
"""

CARD = AgentCard(
    name="pricing_agent",
    description="Predicts optimal ticket pricing and expected event attendance using historical data",
    url="http://pricing-agent:8002",
    domains=["conference", "music_festival", "sporting_event"],
    capabilities=[
        AgentCapability(name="ticket_pricing", description="Recommend pricing tiers"),
        AgentCapability(name="attendance_forecast", description="Predict event attendance"),
        AgentCapability(name="revenue_projection", description="Project revenue and break-even"),
    ],
    input_schema={
        "domain": "string",
        "geography": "string",
        "target_audience": "number",
        "topic": "string",
        "budget_usd": "number"
    },
    output_schema={"pricing_tiers": "object", "attendance_forecast": "object"}
)

class PricingAgent(BaseConferenceAgent):

    def __init__(self):
        super().__init__(CARD, SYSTEM_PROMPT, port=8002)

    async def handle_task(self, task: Task) -> dict:
        user_message = task.messages[0].parts[0].text if task.messages and task.messages[0].parts else ""

        await self.emit_progress(task.id, "Building pricing model...")
        result = await self.llm_with_tools(task, user_message=user_message)

        await self.emit_progress(task.id, "Pricing model complete.")
        artifact = Artifact(
            name="pricing_model",
            parts=[TextPart(text=result)]
        )
        return {"artifact": artifact}