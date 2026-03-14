"""
Ten31 Thoughts - Vector Store
ChromaDB integration for semantic search over transcript chunks and analysis results.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# Chunking parameters
CHUNK_SIZE = 1500  # characters per chunk
CHUNK_OVERLAP = 200  # overlap between chunks


class VectorStore:
    """
    Manages ChromaDB collections for semantic search across all content types.

    Collections:
    - content_chunks: Raw content text chunks (transcripts, articles)
    - thesis_elements: Extracted thesis elements from our content
    - frameworks: Extracted frameworks from external content
    - blind_spots: Detected blind spots
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        import chromadb

        host = host or os.getenv("CHROMADB_HOST", "localhost")
        port = port or int(os.getenv("CHROMADB_PORT", "8000"))

        try:
            self.client = chromadb.HttpClient(host=host, port=port)
            logger.info(f"Connected to ChromaDB at {host}:{port}")
        except Exception:
            # Fall back to embedded mode for local development
            persist_dir = os.getenv("CHROMADB_PERSIST_DIR", "./data/chromadb")
            self.client = chromadb.PersistentClient(path=persist_dir)
            logger.info(f"Using embedded ChromaDB at {persist_dir}")

        self._init_collections()

    def _init_collections(self):
        """Initialize or get all collections."""
        self.content_chunks = self.client.get_or_create_collection(
            name="content_chunks",
            metadata={"description": "Raw content text chunks for RAG retrieval"}
        )
        self.thesis_elements = self.client.get_or_create_collection(
            name="thesis_elements",
            metadata={"description": "Extracted thesis elements from our content"}
        )
        self.frameworks = self.client.get_or_create_collection(
            name="frameworks",
            metadata={"description": "Extracted frameworks from external content"}
        )
        self.blind_spots = self.client.get_or_create_collection(
            name="blind_spots",
            metadata={"description": "Detected analytical blind spots"}
        )

    # ─── Content Chunking & Indexing ───

    def index_content(
        self,
        item_id: str,
        content: str,
        metadata: dict,
    ) -> int:
        """
        Chunk and index raw content text.
        Returns number of chunks created.
        """
        chunks = self._chunk_text(content)
        if not chunks:
            return 0

        ids = [f"{item_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{**metadata, "chunk_index": i} for i in range(len(chunks))]

        # Delete existing chunks for this item (re-indexing)
        try:
            existing = self.content_chunks.get(where={"item_id": item_id})
            if existing and existing["ids"]:
                self.content_chunks.delete(ids=existing["ids"])
        except Exception:
            pass

        self.content_chunks.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )

        return len(chunks)

    def index_thesis_element(
        self,
        element_id: str,
        claim_text: str,
        metadata: dict,
    ):
        """Index a thesis element for semantic search."""
        self.thesis_elements.upsert(
            ids=[element_id],
            documents=[claim_text],
            metadatas=[metadata],
        )

    def index_framework(
        self,
        framework_id: str,
        text: str,
        metadata: dict,
    ):
        """Index an external framework for semantic search."""
        self.frameworks.upsert(
            ids=[framework_id],
            documents=[text],
            metadatas=[metadata],
        )

    def index_blind_spot(
        self,
        spot_id: str,
        text: str,
        metadata: dict,
    ):
        """Index a blind spot for semantic search."""
        self.blind_spots.upsert(
            ids=[spot_id],
            documents=[text],
            metadatas=[metadata],
        )

    # ─── Search ───

    def search_content(
        self,
        query: str,
        n_results: int = 10,
        category: Optional[str] = None,
        feed_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Search raw content chunks.
        Returns list of {id, document, metadata, distance}.
        """
        where = {}
        if category:
            where["category"] = category
        if feed_id:
            where["feed_id"] = feed_id

        results = self.content_chunks.query(
            query_texts=[query],
            n_results=n_results,
            where=where if where else None,
        )

        return self._format_results(results)

    def search_thesis_elements(
        self,
        query: str,
        n_results: int = 10,
        topic: Optional[str] = None,
    ) -> list[dict]:
        """Search thesis elements semantically."""
        where = {}
        if topic:
            where["topic"] = topic

        results = self.thesis_elements.query(
            query_texts=[query],
            n_results=n_results,
            where=where if where else None,
        )

        return self._format_results(results)

    def search_frameworks(
        self,
        query: str,
        n_results: int = 10,
        guest_name: Optional[str] = None,
    ) -> list[dict]:
        """Search external frameworks semantically."""
        where = {}
        if guest_name:
            where["guest_name"] = guest_name

        results = self.frameworks.query(
            query_texts=[query],
            n_results=n_results,
            where=where if where else None,
        )

        return self._format_results(results)

    def search_blind_spots(
        self,
        query: str,
        n_results: int = 10,
        severity: Optional[str] = None,
    ) -> list[dict]:
        """Search blind spots semantically."""
        where = {}
        if severity:
            where["severity"] = severity

        results = self.blind_spots.query(
            query_texts=[query],
            n_results=n_results,
            where=where if where else None,
        )

        return self._format_results(results)

    def search_all(
        self,
        query: str,
        n_results_per_collection: int = 5,
    ) -> dict:
        """
        Search across all collections. Returns results grouped by type.
        Used by the chat RAG pipeline for comprehensive context retrieval.
        """
        return {
            "content": self.search_content(query, n_results_per_collection),
            "thesis_elements": self.search_thesis_elements(query, n_results_per_collection),
            "frameworks": self.search_frameworks(query, n_results_per_collection),
            "blind_spots": self.search_blind_spots(query, n_results_per_collection),
        }

    # ─── Stats ───

    def get_stats(self) -> dict:
        """Get counts for all collections."""
        return {
            "content_chunks": self.content_chunks.count(),
            "thesis_elements": self.thesis_elements.count(),
            "frameworks": self.frameworks.count(),
            "blind_spots": self.blind_spots.count(),
        }

    # ─── Helpers ───

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks for embedding."""
        if not text or len(text.strip()) < 50:
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE

            # Try to break at a paragraph or sentence boundary
            if end < len(text):
                # Look for paragraph break
                para_break = text.rfind("\n\n", start + CHUNK_SIZE // 2, end + 100)
                if para_break > start:
                    end = para_break + 2
                else:
                    # Look for sentence break
                    for sep in [". ", "! ", "? ", ".\n"]:
                        sent_break = text.rfind(sep, start + CHUNK_SIZE // 2, end + 50)
                        if sent_break > start:
                            end = sent_break + len(sep)
                            break

            chunk = text[start:end].strip()
            if chunk and len(chunk) > 50:
                chunks.append(chunk)

            start = end - CHUNK_OVERLAP

        return chunks

    def _format_results(self, results: dict) -> list[dict]:
        """Format ChromaDB query results into a flat list."""
        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        formatted = []
        for i in range(len(results["ids"][0])):
            item = {
                "id": results["ids"][0][i],
                "document": results["documents"][0][i] if results.get("documents") else "",
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                "distance": results["distances"][0][i] if results.get("distances") else None,
            }
            formatted.append(item)

        return formatted
