"""RAG tools over Qdrant activity embeddings."""

from langchain_core.tools import tool

from ..ingestion.embedder import COLLECTION_NAME, embed_text, get_qdrant_client


@tool
async def search_similar_activity(query: str, org_id: str, limit: int = 5) -> list[dict]:
    """Semantic search over activity events for a given org."""
    vector = embed_text(query)
    client = get_qdrant_client()

    results = await client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        query_filter={"must": [{"key": "org_id", "match": {"value": org_id}}]},
        limit=limit,
    )

    return [
        {"score": r.score, **r.payload}
        for r in results
    ]
