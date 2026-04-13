import json
from openai import AsyncAzureOpenAI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from shared.config import config

openai_client = AsyncAzureOpenAI(
    azure_endpoint=config.azure_openai_endpoint,
    api_key=config.azure_openai_api_key,
    api_version=config.azure_openai_api_version
)

async def get_embedding(content: str) -> list[float]:
    response = await openai_client.embeddings.create(
        model=config.azure_openai_embedding_deployment,
        input=[content],
        dimensions=1536
    )
    return response.data[0].embedding

class EpisodicMemory:
    """Vector similarity search over past experiences."""

    def __init__(self, namespace: str, db_url: str):
        self.namespace = namespace
        engine = create_async_engine(db_url.replace("postgresql://", "postgresql+asyncpg://"))
        self.session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def remember(self, content: str, metadata: dict = None):
        """Store a new memory with its embedding."""
        embedding = await get_embedding(content)
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        async with self.session_factory() as session:
            await session.execute(text("""
                INSERT INTO agent_memories (namespace, content, embedding, metadata)
                VALUES (:ns, :content, CAST(:embedding AS vector), CAST(:metadata AS jsonb))
            """), {
                "ns": self.namespace,
                "content": content,
                "embedding": vec_str,
                "metadata": json.dumps(metadata or {})
            })
            await session.commit()

    async def recall(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic search — returns most relevant past memories."""
        embedding = await get_embedding(query)
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        async with self.session_factory() as session:
            result = await session.execute(text("""
                SELECT content, metadata,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM agent_memories
                WHERE namespace = :ns
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """), {"ns": self.namespace, "embedding": vec_str, "limit": limit})
            rows = result.fetchall()
            return [
                {"content": r[0], "metadata": r[1], "score": float(r[2])}
                for r in rows
            ]

    async def recall_cross_namespace(
        self, query: str, namespaces: list[str], limit: int = 10
    ) -> list[dict]:
        """Search across multiple agent namespaces — for seed data shared by all agents."""
        embedding = await get_embedding(query)
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        ns_list = ", ".join(f"'{n}'" for n in namespaces)
        async with self.session_factory() as session:
            result = await session.execute(text(f"""
                SELECT namespace, content, metadata,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM agent_memories
                WHERE namespace IN ({ns_list})
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """), {"embedding": vec_str, "limit": limit})
            rows = result.fetchall()
            return [
                {"namespace": r[0], "content": r[1],
                 "metadata": r[2], "score": float(r[3])}
                for r in rows
            ]