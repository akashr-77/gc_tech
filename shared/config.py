import os
from dataclasses import dataclass
from urllib.parse import quote_plus


def build_default_database_url() -> str:
    """Build a DATABASE_URL from individual POSTGRES_* env vars.

    Used as the fallback when DATABASE_URL is not set explicitly, ensuring
    the connection string always matches what the postgres container creates.
    """
    return "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=quote_plus(os.getenv("POSTGRES_USER", "conference")),
        password=quote_plus(os.getenv("POSTGRES_PASSWORD", "password")),
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        db=os.getenv("POSTGRES_DB", "conference_db"),
    )


@dataclass
class Config:
    # Azure OpenAI
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    model: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    azure_openai_embedding_deployment: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
    embedding_dim: int = 1536

    # Database
    database_url: str = os.getenv("DATABASE_URL", build_default_database_url())

    # MCP Server
    mcp_server_url: str = os.getenv("MCP_SERVER_URL", "http://mcp-server:8080/sse")

    # Registry
    registry_url: str = os.getenv("REGISTRY_URL", "http://registry:9000")

    # Agent URLs
    agent_urls: dict = None

    def __post_init__(self):
        self.agent_urls = {
            "venue_agent":     os.getenv("VENUE_URL", "http://venue-agent:8001"),
            "pricing_agent":   os.getenv("PRICING_URL", "http://pricing-agent:8002"),
            "sponsor_agent":   os.getenv("SPONSOR_URL", "http://sponsor-agent:8003"),
            "speaker_agent":   os.getenv("SPEAKER_URL", "http://speaker-agent:8004"),
            "exhibitor_agent": os.getenv("EXHIBITOR_URL", "http://exhibitor-agent:8005"),
            "community_agent": os.getenv("COMMUNITY_URL", "http://community-agent:8006"),
            "eventops_agent":  os.getenv("EVENTOPS_URL", "http://eventops-agent:8000"),
        }

config = Config()