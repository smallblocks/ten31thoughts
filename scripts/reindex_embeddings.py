#!/usr/bin/env python3
"""
Ten31 Thoughts — Rebuild all ChromaDB collections with provider-backed embeddings.

This script is DESTRUCTIVE: it deletes the three vector collections and recreates
them from SQLite (the source of truth).  It is safe to re-run — a failed or
partial run can simply be retried.

Preconditions
─────────────
1. The DGX Spark (or whichever provider) must serve an embedding model at its
   OpenAI-compatible /v1/embeddings endpoint.
2. `embeddingModel` must be set in the Configure LLM action (store.json) to match
   that model.
3. The provider must be `vllm`, `ollama`, or `openai` — Anthropic has no
   embeddings endpoint.

Post-migration caveat
─────────────────────
Resurfacing distance thresholds (semantic-on-write ~0.5 cutoff, news-driven
similarity) were calibrated against MiniLM cosine distances.  After switching
embedding models the thresholds will need re-tuning.  This script does NOT
adjust them — that is a follow-up task.

Usage
─────
    cd ten31-thoughts
    python scripts/reindex_embeddings.py [--batch-size 32] [--dry-run]

Run ONCE after deploying the embedding-function changes, not on every boot.
"""

import argparse
import logging
import os
import sys
import time

# Ensure the project root is on sys.path so `from src…` works when invoked as
# a standalone script.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.db.models import (
    ContentItem,
    Note,
    Connection,
    get_engine,
    get_session,
)
from src.db.embedding_fn import ConfiguredEmbeddingFunction, ConfigurationError
from src.db.vector import VectorStore, CHUNK_SIZE, CHUNK_OVERLAP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("reindex_embeddings")


# ── helpers ──────────────────────────────────────────────────────────────────

def chunk_text(text: str) -> list[str]:
    """Mirror VectorStore._chunk_text so chunk ids stay consistent."""
    if not text or len(text.strip()) < 50:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            para = text.rfind("\n\n", start + CHUNK_SIZE // 2, end + 100)
            if para > start:
                end = para + 2
            else:
                for sep in [". ", "! ", "? ", ".\n"]:
                    sent = text.rfind(sep, start + CHUNK_SIZE // 2, end + 50)
                    if sent > start:
                        end = sent + len(sep)
                        break
        chunk = text[start:end].strip()
        if chunk and len(chunk) > 50:
            chunks.append(chunk)
        start = end - CHUNK_OVERLAP
    return chunks


def reindex_content(session, vs: VectorStore, batch_size: int, dry_run: bool) -> int:
    """Re-embed all ContentItem rows with non-empty content_text."""
    items = (
        session.query(ContentItem)
        .filter(ContentItem.content_text.isnot(None))
        .filter(ContentItem.content_text != "")
        .all()
    )

    total_chunks = 0
    for item in items:
        chunks = chunk_text(item.content_text)
        if not chunks:
            continue

        ids = [f"{item.item_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "item_id": item.item_id,
                "feed_id": item.feed_id or "",
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        if not dry_run:
            # Batch upsert — ChromaDB will invoke the embedding function
            for b in range(0, len(ids), batch_size):
                vs.content_chunks.add(
                    ids=ids[b : b + batch_size],
                    documents=chunks[b : b + batch_size],
                    metadatas=metadatas[b : b + batch_size],
                )
        total_chunks += len(chunks)

    logger.info(f"content_chunks: {len(items)} items → {total_chunks} chunks")
    return total_chunks


def reindex_notes(session, vs: VectorStore, batch_size: int, dry_run: bool) -> int:
    """Re-embed all non-archived notes with non-empty body."""
    notes = (
        session.query(Note)
        .filter(Note.body.isnot(None))
        .filter(Note.body != "")
        .filter(Note.archived == False)  # noqa: E712
        .all()
    )

    ids = [n.note_id for n in notes]
    docs = [n.body for n in notes]
    metas = [
        {
            "topic": n.topic or "",
            "conviction_tier": n.conviction_tier or "",
        }
        for n in notes
    ]

    if not dry_run:
        for b in range(0, len(ids), batch_size):
            vs.notes.add(
                ids=ids[b : b + batch_size],
                documents=docs[b : b + batch_size],
                metadatas=metas[b : b + batch_size],
            )

    logger.info(f"notes: {len(notes)} indexed")
    return len(notes)


def reindex_connections(session, vs: VectorStore, batch_size: int, dry_run: bool) -> int:
    """Re-embed all connections with non-empty articulation."""
    conns = (
        session.query(Connection)
        .filter(Connection.articulation.isnot(None))
        .filter(Connection.articulation != "")
        .all()
    )

    ids = [c.connection_id for c in conns]
    docs = [c.articulation for c in conns]
    metas = [
        {
            "item_id": c.item_id or "",
            "note_id": c.note_id or "",
            "relation": c.relation or "",
        }
        for c in conns
    ]

    if not dry_run:
        for b in range(0, len(ids), batch_size):
            vs.connections.add(
                ids=ids[b : b + batch_size],
                documents=docs[b : b + batch_size],
                metadatas=metas[b : b + batch_size],
            )

    logger.info(f"connections: {len(conns)} indexed")
    return len(conns)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Rebuild ChromaDB collections with provider-backed embeddings."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Documents per embedding call (default 32).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows without writing to ChromaDB.",
    )
    args = parser.parse_args()

    # ── 1. Validate embedding config ────────────────────────────────────────
    try:
        emb_fn = ConfiguredEmbeddingFunction()
    except ConfigurationError as e:
        logger.error(f"Embedding configuration error: {e}")
        sys.exit(1)

    # Quick smoke test — embed one string to verify the endpoint is reachable
    logger.info("Smoke-testing embedding endpoint…")
    try:
        result = emb_fn(["hello world"])
        dim = len(result[0])
        logger.info(f"Endpoint OK — embedding dimension: {dim}")
    except Exception as e:
        logger.error(f"Embedding endpoint unreachable: {e}")
        sys.exit(1)

    # ── 2. Open SQLite ──────────────────────────────────────────────────────
    engine = get_engine()
    db_session = get_session(engine)

    # ── 3. Delete and recreate collections ──────────────────────────────────
    import chromadb

    chroma_host = os.getenv("CHROMADB_HOST", "localhost")
    chroma_port = int(os.getenv("CHROMADB_PORT", "8000"))

    try:
        client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    except Exception:
        persist_dir = os.getenv("CHROMADB_PERSIST_DIR", "./data/chromadb")
        client = chromadb.PersistentClient(path=persist_dir)

    if not args.dry_run:
        for name in ("content_chunks", "notes", "connections"):
            try:
                client.delete_collection(name)
                logger.info(f"Deleted collection: {name}")
            except Exception:
                logger.info(f"Collection '{name}' did not exist — skipping delete")

    # ── 4. Construct VectorStore (recreates collections with embedding fn) ──
    vs = VectorStore()

    # ── 5. Re-index from SQLite ─────────────────────────────────────────────
    t0 = time.time()

    n_chunks = reindex_content(db_session, vs, args.batch_size, args.dry_run)
    n_notes = reindex_notes(db_session, vs, args.batch_size, args.dry_run)
    n_conns = reindex_connections(db_session, vs, args.batch_size, args.dry_run)

    elapsed = time.time() - t0

    # ── 6. Verify ───────────────────────────────────────────────────────────
    if not args.dry_run:
        stats = vs.get_stats()
        logger.info(f"Final collection counts: {stats}")
    else:
        logger.info("[dry-run] Would index: "
                     f"{n_chunks} content chunks, {n_notes} notes, {n_conns} connections")

    logger.info(f"Reindex complete in {elapsed:.1f}s")

    db_session.close()


if __name__ == "__main__":
    main()
