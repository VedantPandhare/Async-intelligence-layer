import uuid
from datetime import datetime

from huggingface_hub import InferenceClient
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.activity_event import ActivityEvent
from .normalizer import NormalizedEvent

settings = get_settings()

_hf_client: InferenceClient | None = None
_qdrant_client: AsyncQdrantClient | None = None

COLLECTION_NAME = "activity_embeddings"


def get_hf_client() -> InferenceClient:
    global _hf_client
    if _hf_client is None:
        _hf_client = InferenceClient(token=settings.hf_token)
    return _hf_client


def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host, port=settings.qdrant_port
        )
    return _qdrant_client


async def ensure_collection() -> None:
    """Create Qdrant collection if it doesn't exist."""
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE,
            ),
        )


def embed_text(text: str) -> list[float]:
    """Embed a string via HuggingFace Inference API (BAAI/bge-base-en-v1.5)."""
    client = get_hf_client()
    result = client.feature_extraction(text, model=settings.hf_embedding_model)
    # result is a nested list — average pool if needed
    if isinstance(result[0], list):
        # sentence-level output: take first token (CLS) or mean pool
        import numpy as np
        vector = np.mean(result, axis=0).tolist()
    else:
        vector = list(result)
    return vector


async def embed_and_store_event(
    event: NormalizedEvent,
    activity_event_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Embed event summary, update the DB row, and upsert into Qdrant."""
    vector = embed_text(event.summary)

    # Update pgvector column
    stmt = select(ActivityEvent).where(ActivityEvent.id == activity_event_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record:
        record.embedding = vector
        await db.flush()

    # Upsert into Qdrant
    await ensure_collection()
    client = get_qdrant_client()
    await client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=str(activity_event_id),
                vector=vector,
                payload={
                    "developer_id": event.developer_id,
                    "org_id": event.org_id,
                    "event_type": event.event_type,
                    "source": event.source,
                    "event_time": event.event_time.isoformat(),
                    "summary": event.summary,
                },
            )
        ],
    )
