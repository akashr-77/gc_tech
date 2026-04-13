"""
Tests for the extract_json helper used by both BaseConferenceAgent and EventOpsAgent.

These tests verify that the JSON extraction handles all common LLM output formatting
issues: preamble text, markdown fences, trailing commentary, and clean JSON pass-through.
"""

import json

import pytest

from agents.base_agent import BaseConferenceAgent, extract_json
from agents.eventops_agent.agent import EventOpsAgent


# ---------------------------------------------------------------------------
# Test the module-level extract_json function directly
# ---------------------------------------------------------------------------

class TestExtractJsonFunction:
    """Verify the shared extract_json function works correctly."""

    def test_clean_json_passthrough(self):
        """Pure JSON should pass through unchanged."""
        raw = '{"venue": "Grand Hall", "price_usd": 5000}'
        result = extract_json(raw)
        assert result == raw
        parsed = json.loads(result)
        assert parsed["venue"] == "Grand Hall"

    def test_strips_markdown_fences(self):
        """JSON wrapped in ```json ... ``` should be extracted."""
        raw = '```json\n{"venue": "Grand Hall", "price_usd": 5000}\n```'
        result = extract_json(raw)
        parsed = json.loads(result)
        assert parsed["venue"] == "Grand Hall"

    def test_strips_markdown_fences_without_language(self):
        """JSON wrapped in ``` ... ``` (no language tag) should be extracted."""
        raw = '```\n{"venue": "Grand Hall"}\n```'
        result = extract_json(raw)
        parsed = json.loads(result)
        assert parsed["venue"] == "Grand Hall"

    def test_does_not_match_javascript_fence(self):
        """```javascript ... ``` should NOT be matched as JSON fence."""
        raw = '```javascript\nvar x = {"venue": "Grand Hall"};\n```'
        result = extract_json(raw)
        # Should fall through to brace-matching, not fence extraction
        parsed = json.loads(result)
        assert parsed["venue"] == "Grand Hall"

    def test_strips_preamble_text(self):
        """Preamble text before JSON should be stripped."""
        raw = 'Here is the compiled event plan:\n\n{"venue": "Grand Hall", "capacity": 1000}'
        result = extract_json(raw)
        parsed = json.loads(result)
        assert parsed["venue"] == "Grand Hall"
        assert parsed["capacity"] == 1000

    def test_strips_preamble_and_markdown_fences(self):
        """Preamble + markdown fences should both be stripped."""
        raw = (
            'Here is the plan for the AI conference:\n\n'
            '```json\n'
            '{"event": "AI Conference", "budget_usd": 500000}\n'
            '```\n\n'
            'Let me know if you need changes.'
        )
        result = extract_json(raw)
        parsed = json.loads(result)
        assert parsed["event"] == "AI Conference"
        assert parsed["budget_usd"] == 500000

    def test_nested_json_objects(self):
        """Nested JSON with inner braces should be extracted correctly."""
        inner = {
            "venue": {"name": "Grand Hall", "address": {"city": "Bangalore"}},
            "pricing": {"early_bird": 100, "vip": 500}
        }
        raw = f'The results are:\n{json.dumps(inner)}\nEnd of results.'
        result = extract_json(raw)
        parsed = json.loads(result)
        assert parsed["venue"]["address"]["city"] == "Bangalore"

    def test_non_json_passthrough(self):
        """If no valid JSON found, return original string."""
        raw = "This is just plain text with no JSON."
        result = extract_json(raw)
        assert result == raw

    def test_empty_string(self):
        """Empty string should pass through."""
        result = extract_json("")
        assert result == ""


# ---------------------------------------------------------------------------
# Test _extract_json on BaseConferenceAgent (delegates to extract_json)
# ---------------------------------------------------------------------------

class TestBaseAgentExtractJson:
    """Verify BaseConferenceAgent._extract_json delegates correctly."""

    def test_clean_json_passthrough(self):
        raw = '{"venue": "Grand Hall", "price_usd": 5000}'
        result = BaseConferenceAgent._extract_json(raw)
        assert result == raw
        parsed = json.loads(result)
        assert parsed["venue"] == "Grand Hall"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"venue": "Grand Hall", "price_usd": 5000}\n```'
        result = BaseConferenceAgent._extract_json(raw)
        parsed = json.loads(result)
        assert parsed["venue"] == "Grand Hall"


# ---------------------------------------------------------------------------
# Test _extract_json on EventOpsAgent (delegates to extract_json)
# ---------------------------------------------------------------------------

class TestEventOpsExtractJson:
    """Verify EventOpsAgent._extract_json handles the exact format from the bug report."""

    def test_exact_bug_report_format(self):
        """Reproduce the exact format from the problem statement and verify extraction."""
        raw_actual = (
            'Here is the compiled event plan for the Artificial Intelligence conference:\n\n'
            '```json\n'
            '{"venue_options": [{"name": "Skyye"}], "revenue_forecast": 8750000}'
            '\n```'
        )
        result = EventOpsAgent._extract_json(raw_actual)
        parsed = json.loads(result)
        assert parsed["venue_options"][0]["name"] == "Skyye"
        assert parsed["revenue_forecast"] == 8750000

    def test_full_plan_with_preamble(self):
        """Full event plan JSON wrapped with LLM chattiness."""
        plan = {
            "event_details": {"name": "AI Conference", "location": "Bangalore"},
            "venue_options": [{"name": "Grand Hall", "price_per_day_usd": 8000}],
            "ticket_pricing_tiers": [
                {"tier_name": "Early Bird", "price_usd": 90, "quantity": 200}
            ],
            "revenue_forecast_usd": 105000,
            "speakers": [{"name": "Dr. Smith", "expertise": "AI"}],
            "sponsors": [{"company_name": "Google", "estimated_ask_usd": 150000}],
            "exhibitors": [{"company_name": "StartupAI", "cluster": "ML Tools"}],
            "community_gtm_strategy": {"primary_channels": ["LinkedIn", "Twitter"]}
        }
        raw = f"Here is the compiled event plan:\n\n```json\n{json.dumps(plan, indent=2)}\n```\n\nLet me know!"
        result = EventOpsAgent._extract_json(raw)
        parsed = json.loads(result)
        assert parsed["revenue_forecast_usd"] == 105000
        assert len(parsed["venue_options"]) == 1
        assert parsed["sponsors"][0]["estimated_ask_usd"] == 150000
