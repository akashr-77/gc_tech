"""
Unit tests for social / external-API tools:
  search_reddit, read_reddit_post, search_github, read_github_repo
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# search_reddit
# ---------------------------------------------------------------------------

class TestSearchReddit:
    """Verify Reddit search formatting and subreddit scoping."""

    @pytest.mark.asyncio
    async def test_global_search(self):
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Best AI conferences 2026",
                            "url": "https://reddit.com/r/tech/1",
                            "score": 150,
                            "subreddit": "technology",
                            "permalink": "/r/technology/comments/abc/best_ai/",
                            "selftext": "Looking for recommendations...",
                            "num_comments": 42,
                        }
                    }
                ]
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import search_reddit
            results = await search_reddit("AI conferences")

        assert len(results) == 1
        assert results[0]["title"] == "Best AI conferences 2026"
        assert results[0]["subreddit"] == "technology"
        assert results[0]["score"] == 150

        # Verify global search URL was used
        call_args = mock_client.get.call_args
        assert "reddit.com/search.json" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_subreddit_scoped_search(self):
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"data": {"children": []}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import search_reddit
            await search_reddit("venue reviews", subreddit="conferences")

        call_args = mock_client.get.call_args
        assert "/r/conferences/search.json" in call_args[0][0]


# ---------------------------------------------------------------------------
# read_reddit_post
# ---------------------------------------------------------------------------

class TestReadRedditPost:
    """Verify Reddit post+comments parsing."""

    @pytest.mark.asyncio
    async def test_reads_post_and_comments(self):
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = [
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Event venue feedback",
                                "author": "user123",
                                "subreddit": "events",
                                "score": 200,
                                "selftext": "Has anyone used Convention Center X?",
                                "url": "https://reddit.com/r/events/abc",
                                "num_comments": 15,
                            }
                        }
                    ]
                }
            },
            {
                "data": {
                    "children": [
                        {
                            "kind": "t1",
                            "data": {
                                "author": "commenter1",
                                "body": "Yes, great venue with excellent AV.",
                                "score": 50,
                            },
                        },
                        {
                            "kind": "t1",
                            "data": {
                                "author": "commenter2",
                                "body": "Parking is terrible though.",
                                "score": 30,
                            },
                        },
                    ]
                }
            },
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import read_reddit_post
            result = await read_reddit_post("https://reddit.com/r/events/comments/abc/event_venue/")

        assert result["title"] == "Event venue feedback"
        assert result["author"] == "user123"
        assert len(result["comments"]) == 2
        assert result["comments"][0]["author"] == "commenter1"


# ---------------------------------------------------------------------------
# search_github
# ---------------------------------------------------------------------------

class TestSearchGitHub:
    """Verify GitHub repository search formatting."""

    @pytest.mark.asyncio
    async def test_returns_formatted_repos(self):
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "items": [
                {
                    "full_name": "org/ml-framework",
                    "description": "A machine learning framework",
                    "stargazers_count": 5000,
                    "language": "Python",
                    "html_url": "https://github.com/org/ml-framework",
                    "topics": ["ml", "ai"],
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import search_github
            results = await search_github("machine learning", limit=1)

        assert len(results) == 1
        assert results[0]["name"] == "org/ml-framework"
        assert results[0]["stars"] == 5000
        assert results[0]["language"] == "Python"


# ---------------------------------------------------------------------------
# read_github_repo
# ---------------------------------------------------------------------------

class TestReadGitHubRepo:
    """Verify GitHub repo file/readme reading."""

    @pytest.mark.asyncio
    async def test_reads_readme(self):
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.text = "# ML Framework\n\nA powerful ML toolkit."

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import read_github_repo
            result = await read_github_repo("org", "ml-framework")

        assert "ML Framework" in result
        # Should hit the /readme endpoint
        call_url = mock_client.get.call_args[0][0]
        assert "/readme" in call_url

    @pytest.mark.asyncio
    async def test_reads_specific_file(self):
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.text = "print('hello world')"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_server.server.httpx.AsyncClient", return_value=mock_client):
            from mcp_server.server import read_github_repo
            result = await read_github_repo("org", "ml-framework", path="src/main.py")

        assert "hello world" in result
        call_url = mock_client.get.call_args[0][0]
        assert "/contents/src/main.py" in call_url
