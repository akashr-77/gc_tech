"""
Unit tests for the web-facing MCP tools:
  web_search, scrape_page, get_youtube_transcript, read_rss_feed
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

class TestWebSearch:
    """Verify that web_search delegates to DuckDuckGo and reshapes results."""

    @pytest.mark.asyncio
    async def test_returns_formatted_results(self):
        """web_search calls asyncio.to_thread(_search), where _search uses
        DDGS().text().  The tool then reformats the raw dicts.  We mock
        to_thread to run the inner function with a patched DDGS."""
        fake_ddgs_results = [
            {"title": "AI Conf 2026", "href": "https://example.com/ai", "body": "Top AI conference"},
            {"title": "ML Summit", "href": "https://example.com/ml", "body": "Machine learning event"},
        ]

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = fake_ddgs_results
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        async def run_sync_fn(fn):
            return fn()

        with patch("mcp_server.server.asyncio.to_thread", side_effect=run_sync_fn):
            with patch("ddgs.DDGS", return_value=mock_ddgs_instance):
                from mcp_server.server import web_search
                results = await web_search("AI conferences", num_results=2)

        assert len(results) == 2
        assert results[0]["title"] == "AI Conf 2026"
        assert results[0]["url"] == "https://example.com/ai"
        assert results[0]["snippet"] == "Top AI conference"

    @pytest.mark.asyncio
    async def test_empty_results(self):
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = []
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

        async def run_sync_fn(fn):
            return fn()

        with patch("mcp_server.server.asyncio.to_thread", side_effect=run_sync_fn):
            with patch("ddgs.DDGS", return_value=mock_ddgs_instance):
                from mcp_server.server import web_search
                results = await web_search("nonexistent gibberish xyzzy", num_results=5)

        assert results == []


# ---------------------------------------------------------------------------
# scrape_page
# ---------------------------------------------------------------------------

class TestScrapePage:
    """Verify that scrape_page fetches via Jina Reader first, then falls back."""

    @pytest.mark.asyncio
    async def test_jina_success(self):
        mock_response = MagicMock()
        mock_response.text = "Scraped page content about venue details"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import scrape_page
            result = await scrape_page("https://example.com/venue")

        assert result == "Scraped page content about venue details"
        # Verify it used Jina URL
        mock_client.get.assert_awaited_once()
        call_args = mock_client.get.call_args
        assert "r.jina.ai" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_fallback_on_jina_failure(self):
        """When Jina fails, the tool falls back to direct HTTP fetch."""
        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:
                # Jina fails
                resp.raise_for_status = MagicMock(side_effect=Exception("Jina down"))
                return resp
            else:
                # Fallback succeeds
                resp.text = "Fallback content"
                return resp

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import scrape_page
            result = await scrape_page("https://example.com/page")

        assert result == "Fallback content"


# ---------------------------------------------------------------------------
# get_youtube_transcript
# ---------------------------------------------------------------------------

class TestGetYoutubeTranscript:
    """Verify YouTube transcript extraction and URL parsing."""

    @pytest.mark.asyncio
    async def test_extracts_transcript(self):
        fake_transcript = [
            {"text": "Hello everyone,"},
            {"text": "welcome to the conference."},
            {"text": "Today we discuss AI."},
        ]

        # The server code does `from youtube_transcript_api import YouTubeTranscriptApi`
        # inside _extract(), then calls YouTubeTranscriptApi.get_transcript().
        # We need to mock the class so that .get_transcript returns our data.
        mock_api_class = MagicMock()
        mock_api_class.get_transcript = MagicMock(return_value=fake_transcript)

        async def fake_to_thread(fn):
            return fn()

        with patch("mcp_server.server.asyncio.to_thread", side_effect=fake_to_thread):
            with patch.dict(
                "sys.modules",
                {"youtube_transcript_api": MagicMock(YouTubeTranscriptApi=mock_api_class)},
            ):
                # Re-import so the patched module is picked up inside _extract
                import importlib, mcp_server.server
                importlib.reload(mcp_server.server)
                from mcp_server.server import get_youtube_transcript
                result = await get_youtube_transcript(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                )

        assert "Hello everyone," in result
        assert "welcome to the conference." in result
        assert "Today we discuss AI." in result

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self):
        async def fake_to_thread(fn):
            return fn()

        with patch("mcp_server.server.asyncio.to_thread", side_effect=fake_to_thread):
            from mcp_server.server import get_youtube_transcript
            # URL without valid video ID
            with pytest.raises(ValueError, match="Could not extract video ID"):
                await get_youtube_transcript("https://example.com/not-a-video")


# ---------------------------------------------------------------------------
# read_rss_feed
# ---------------------------------------------------------------------------

class TestReadRssFeed:
    """Verify RSS feed parsing and result shaping."""

    @pytest.mark.asyncio
    async def test_parses_feed(self):
        fake_feed = MagicMock()
        fake_feed.bozo = False
        fake_feed.feed = {"title": "Tech News", "description": "Latest tech"}
        fake_feed.entries = [
            {"title": "Entry 1", "link": "https://a.com/1", "summary": "Summary 1", "published": "2026-01-01"},
            {"title": "Entry 2", "link": "https://a.com/2", "summary": "Summary 2", "published": "2026-01-02"},
        ]

        async def fake_to_thread(fn):
            return fn()

        with patch("mcp_server.server.asyncio.to_thread", side_effect=fake_to_thread):
            with patch("feedparser.parse", return_value=fake_feed):
                from mcp_server.server import read_rss_feed
                result = await read_rss_feed("https://example.com/feed.xml")

        assert result["title"] == "Tech News"
        assert len(result["items"]) == 2
        assert result["items"][0]["title"] == "Entry 1"

    @pytest.mark.asyncio
    async def test_bozo_feed_raises(self):
        """A malformed feed with no entries should raise RuntimeError."""
        fake_feed = MagicMock()
        fake_feed.bozo = True
        fake_feed.entries = []
        fake_feed.get = MagicMock(return_value="parse error")

        async def fake_to_thread(fn):
            return fn()

        with patch("mcp_server.server.asyncio.to_thread", side_effect=fake_to_thread):
            with patch("feedparser.parse", return_value=fake_feed):
                from mcp_server.server import read_rss_feed
                with pytest.raises(RuntimeError, match="Failed to parse RSS"):
                    await read_rss_feed("https://bad.com/feed.xml")
