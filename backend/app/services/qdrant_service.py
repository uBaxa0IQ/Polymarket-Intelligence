"""Qdrant vector store for historical Polymarket market outcomes (RAG Phase 1)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION = "polymarket_markets"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2


def _stable_point_id(market_id: str) -> int:
    """Qdrant point id must be stable across processes. Built-in hash() is randomized (PYTHONHASHSEED)."""
    digest = hashlib.sha256(market_id.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big") % (2**63)


def _qdrant_url() -> str:
    return os.getenv("QDRANT_URL", "http://localhost:6333")


# ---------------------------------------------------------------------------
# Embedding — lazy-loaded singleton so the model downloads once on first use
# ---------------------------------------------------------------------------

_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded sentence-transformer: all-MiniLM-L6-v2")
    return _embed_model


def _embed(text: str) -> list[float]:
    model = _get_embed_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


# ---------------------------------------------------------------------------
# Qdrant client — lazy singleton
# ---------------------------------------------------------------------------

_qdrant_client = None


def _get_client():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        _qdrant_client = QdrantClient(url=_qdrant_url())
    return _qdrant_client


def _ensure_collection() -> None:
    from qdrant_client.http.exceptions import UnexpectedResponse
    from qdrant_client.models import Distance, VectorParams
    client = _get_client()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        try:
            client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s", COLLECTION)
        except UnexpectedResponse as exc:
            if exc.status_code != 409:
                raise
            logger.debug("Qdrant collection already exists (parallel create): %s", COLLECTION)


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class QdrantService:
    async def upsert_resolved_market(
        self,
        *,
        market_id: str,
        question: str,
        outcome: str,          # "yes" or "no"
        p_market: float | None,
        p_yes_estimated: float | None,
        pnl: float | None,
        resolved_at: str | None,
    ) -> None:
        """Embed market question and store resolved outcome in Qdrant."""
        try:
            await asyncio.to_thread(self._upsert_sync, market_id=market_id, question=question,
                                    outcome=outcome, p_market=p_market,
                                    p_yes_estimated=p_yes_estimated, pnl=pnl,
                                    resolved_at=resolved_at)
        except Exception as exc:
            logger.warning("Qdrant upsert failed for %s: %s", market_id, exc)

    def _upsert_sync(self, *, market_id, question, outcome, p_market,
                     p_yes_estimated, pnl, resolved_at) -> None:
        from qdrant_client.models import PointStruct
        _ensure_collection()
        vector = _embed(question)
        point_id = _stable_point_id(market_id)
        payload: dict[str, Any] = {
            "market_id": market_id,
            "question": question,
            "outcome": outcome,
            "p_market": p_market,
            "p_yes_estimated": p_yes_estimated,
            "pnl": pnl,
            "resolved_at": resolved_at,
        }
        _get_client().upsert(
            collection_name=COLLECTION,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        logger.debug("Qdrant upsert OK: market_id=%s outcome=%s", market_id, outcome)

    async def search_similar(self, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Find top-k resolved markets most similar to the given question."""
        try:
            return await asyncio.to_thread(self._search_sync, question, top_k)
        except Exception as exc:
            logger.warning("Qdrant search failed: %s", exc)
            return []

    def _search_sync(self, question: str, top_k: int) -> list[dict[str, Any]]:
        _ensure_collection()
        vector = _embed(question)
        resp = _get_client().query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=top_k,
            with_payload=True,
            score_threshold=0.5,  # ignore very dissimilar markets
        )
        hits = resp.points
        results = []
        for hit in hits:
            p = hit.payload or {}
            results.append({
                "question": p.get("question", ""),
                "outcome": p.get("outcome", ""),
                "p_market": p.get("p_market"),
                "p_yes_estimated": p.get("p_yes_estimated"),
                "pnl": p.get("pnl"),
                "resolved_at": p.get("resolved_at"),
                "similarity": round(hit.score, 3),
            })
        return results

    def format_for_prompt(self, similar: list[dict[str, Any]]) -> str:
        """Format similar markets as a text block to inject into Base Rate prompt."""
        if not similar:
            return ""
        lines = ["=== SIMILAR RESOLVED MARKETS (from our own historical bets) ==="]
        for i, m in enumerate(similar, 1):
            outcome = str(m.get("outcome", "?")).upper()
            q = m.get("question", "?")
            pm = m.get("p_market")
            pe = m.get("p_yes_estimated")
            pnl = m.get("pnl")
            sim = m.get("similarity", 0)
            pm_str = f"market_price={pm:.2f}" if pm is not None else ""
            pe_str = f"our_estimate={pe:.2f}" if pe is not None else ""
            pnl_str = f"pnl=${pnl:+.2f}" if pnl is not None else ""
            meta = ", ".join(x for x in [pm_str, pe_str, pnl_str] if x)
            lines.append(f"{i}. [{outcome}] \"{q}\" ({meta}, similarity={sim})")
        lines.append("")
        return "\n".join(lines)


qdrant_service = QdrantService()
