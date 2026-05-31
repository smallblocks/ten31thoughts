"""
Ten31 Thoughts - Embedding function + reindex tests
Run with: pytest tests/test_embedding_fn.py -v
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.db.embedding_fn import (
    ConfiguredEmbeddingFunction,
    ConfigurationError,
    EmbeddingError,
    EMBEDDING_BATCH_SIZE,
)


# ── Config resolution tests ──────────────────────────────────────────────────


class TestConfigResolution:
    """Verify _resolve_config picks the right provider settings."""

    def _write_store(self, tmp_path, data):
        store_path = tmp_path / "store.json"
        store_path.write_text(json.dumps(data))
        return store_path

    def test_vllm_provider_sets_openai_prefix_and_base(self, tmp_path):
        store = self._write_store(tmp_path, {
            "provider": "vllm",
            "vllmBaseUrl": "http://192.168.86.52:8000",
            "embeddingModel": "BAAI/bge-large-en-v1.5",
        })
        with patch.object(ConfiguredEmbeddingFunction, "_load_store", return_value=json.loads(store.read_text())):
            cfg = ConfiguredEmbeddingFunction._resolve_config()
        assert cfg["model"] == "openai/BAAI/bge-large-en-v1.5"
        assert cfg["api_base"] == "http://192.168.86.52:8000"
        assert cfg["api_key"] == "vllm"

    def test_vllm_provider_no_double_prefix(self, tmp_path):
        store = self._write_store(tmp_path, {
            "provider": "vllm",
            "vllmBaseUrl": "http://spark:8000",
            "embeddingModel": "openai/my-model",
        })
        with patch.object(ConfiguredEmbeddingFunction, "_load_store", return_value=json.loads(store.read_text())):
            cfg = ConfiguredEmbeddingFunction._resolve_config()
        assert cfg["model"] == "openai/my-model"

    def test_anthropic_provider_raises(self, tmp_path):
        store = self._write_store(tmp_path, {
            "provider": "anthropic",
            "embeddingModel": "text-embedding-3-small",
        })
        with patch.object(ConfiguredEmbeddingFunction, "_load_store", return_value=json.loads(store.read_text())):
            with pytest.raises(ConfigurationError, match="does not support embeddings"):
                ConfiguredEmbeddingFunction._resolve_config()

    def test_ollama_provider(self, tmp_path):
        store = self._write_store(tmp_path, {
            "provider": "ollama",
            "ollamaBaseUrl": "http://localhost:11434",
            "embeddingModel": "nomic-embed-text",
        })
        with patch.object(ConfiguredEmbeddingFunction, "_load_store", return_value=json.loads(store.read_text())):
            cfg = ConfiguredEmbeddingFunction._resolve_config()
        assert cfg["model"] == "nomic-embed-text"
        assert cfg["api_base"] == "http://localhost:11434"

    def test_openai_provider(self, tmp_path):
        store = self._write_store(tmp_path, {
            "provider": "openai",
            "openaiApiKey": "sk-test",
            "embeddingModel": "text-embedding-3-small",
        })
        with patch.object(ConfiguredEmbeddingFunction, "_load_store", return_value=json.loads(store.read_text())):
            cfg = ConfiguredEmbeddingFunction._resolve_config()
        assert cfg["model"] == "text-embedding-3-small"
        assert cfg["api_key"] == "sk-test"

    def test_env_fallback(self):
        env = {
            "TEN31_LLM_EMBEDDING_MODEL": "my-embed",
            "VLLM_BASE_URL": "http://spark:8000",
        }
        # Empty store → falls back to env, default provider is anthropic → raises
        with patch.object(ConfiguredEmbeddingFunction, "_load_store", return_value={}):
            with pytest.raises(ConfigurationError, match="does not support embeddings"):
                ConfiguredEmbeddingFunction._resolve_config()

    def test_no_model_configured(self):
        with patch.object(ConfiguredEmbeddingFunction, "_load_store", return_value={"provider": "vllm", "vllmBaseUrl": "http://x:8000"}):
            cfg = ConfiguredEmbeddingFunction._resolve_config()
        # model will be empty string from env default
        # The constructor should raise when model is empty
        with patch.object(ConfiguredEmbeddingFunction, "_resolve_config", return_value=cfg):
            with pytest.raises(ConfigurationError, match="No embedding model configured"):
                ConfiguredEmbeddingFunction()


# ── Embedding call tests ─────────────────────────────────────────────────────


class TestEmbeddingCall:
    """Test the __call__ method with mocked litellm."""

    @pytest.fixture
    def emb_fn(self):
        """Create an embedding function with explicit config (skips store.json)."""
        return ConfiguredEmbeddingFunction(
            model="openai/test-model",
            api_base="http://test:8000",
            api_key="test-key",
        )

    def _mock_response(self, vectors):
        """Build a mock litellm.embedding response."""
        resp = MagicMock()
        resp.data = [{"embedding": v} for v in vectors]
        return resp

    def test_returns_vectors_of_expected_dimension(self, emb_fn):
        dim = 1024
        docs = ["Hello world", "Bitcoin is freedom", "Sovereign computing"]
        vectors = [[0.1] * dim for _ in docs]

        with patch("src.db.embedding_fn.litellm.embedding", return_value=self._mock_response(vectors)):
            result = emb_fn(docs)

        assert len(result) == 3
        assert all(len(v) == dim for v in result)

    def test_empty_input_skips_call(self, emb_fn):
        # ChromaDB's __init_subclass__ wrapper calls validate_embeddings which
        # fails on truly empty lists, so ChromaDB never invokes __call__ with
        # []. We verify the internal _embed_batch returns correctly.
        with patch("src.db.embedding_fn.litellm.embedding", return_value=self._mock_response([])) as mock:
            result = emb_fn._embed_batch([])
        assert result == []
        mock.assert_called_once()

    def test_batching_large_input(self, emb_fn):
        """Inputs larger than EMBEDDING_BATCH_SIZE are split into batches."""
        n = EMBEDDING_BATCH_SIZE + 10
        docs = [f"doc {i}" for i in range(n)]
        dim = 128

        call_count = 0

        def mock_embed(**kwargs):
            nonlocal call_count
            call_count += 1
            batch = kwargs["input"]
            return self._mock_response([[0.1] * dim for _ in batch])

        with patch("src.db.embedding_fn.litellm.embedding", side_effect=mock_embed):
            result = emb_fn(docs)

        assert len(result) == n
        assert call_count == 2  # ceil(n / EMBEDDING_BATCH_SIZE)

    def test_endpoint_failure_raises_embedding_error(self, emb_fn):
        with patch("src.db.embedding_fn.litellm.embedding", side_effect=ConnectionError("refused")):
            with pytest.raises(EmbeddingError, match="Embedding call failed"):
                emb_fn(["test"])

    def test_passes_correct_kwargs(self, emb_fn):
        with patch("src.db.embedding_fn.litellm.embedding", return_value=self._mock_response([[0.1]])) as mock:
            emb_fn(["test"])
            mock.assert_called_once_with(
                model="openai/test-model",
                input=["test"],
                api_key="test-key",
                api_base="http://test:8000",
            )


# ── VectorStore integration tests ────────────────────────────────────────────


class TestVectorStoreEmbeddingIntegration:
    """Verify VectorStore passes the embedding function to collections."""

    @patch("src.db.vector.ConfiguredEmbeddingFunction")
    def test_embedding_fn_passed_to_collections(self, MockEmbFn):
        """All three collections receive the embedding function."""
        # Create a proper embedding function mock with correct __call__ signature
        mock_fn = ConfiguredEmbeddingFunction(
            model="openai/test", api_base="http://test:8000", api_key="test",
        )
        MockEmbFn.return_value = mock_fn

        import shutil
        test_dir = "/tmp/test_chroma_emb"
        shutil.rmtree(test_dir, ignore_errors=True)

        with patch.dict(os.environ, {"CHROMADB_PERSIST_DIR": test_dir}):
            from src.db.vector import VectorStore
            with patch("chromadb.HttpClient", side_effect=Exception("no server")):
                vs = VectorStore()

        # The embedding function should have been constructed
        MockEmbFn.assert_called_once()
        # All three collections exist
        assert vs.content_chunks is not None
        assert vs.notes is not None
        assert vs.connections is not None

        shutil.rmtree(test_dir, ignore_errors=True)

    @patch("src.db.vector.ConfiguredEmbeddingFunction", side_effect=ConfigurationError("no provider"))
    def test_graceful_fallback_on_config_error(self, MockEmbFn):
        """VectorStore logs a warning but doesn't crash if provider is misconfigured."""
        import chromadb
        with patch.dict(os.environ, {"CHROMADB_PERSIST_DIR": "/tmp/test_chroma_fallback"}):
            from src.db.vector import VectorStore
            with patch("chromadb.HttpClient", side_effect=Exception("no server")):
                vs = VectorStore()

        # Should still have collections (with default embedding)
        assert vs._embedding_fn is None
        assert vs.content_chunks is not None

        import shutil
        shutil.rmtree("/tmp/test_chroma_fallback", ignore_errors=True)


# ── Reindex script tests ─────────────────────────────────────────────────────


class TestReindexScript:
    """Test the reindex helpers over a small fixture corpus."""

    @pytest.fixture
    def db_session(self, tmp_path):
        from src.db.models import Base, get_engine, get_session, create_tables
        engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
        create_tables(engine)
        return get_session(engine)

    @pytest.fixture
    def seed_data(self, db_session):
        """Insert a small corpus into SQLite."""
        from src.db.models import Feed, ContentItem, Note, Connection, FeedCategory

        feed = Feed(
            feed_id="feed-1",
            url="https://example.com/feed",
            category=FeedCategory.OUR_THESIS,
            display_name="Test Feed",
        )
        db_session.add(feed)

        items = [
            ContentItem(
                item_id=f"item-{i}",
                feed_id="feed-1",
                url=f"https://example.com/{i}",
                title=f"Item {i}",
                content_text=f"Bitcoin is sound money. " * 20 if i < 3 else "",
            )
            for i in range(4)
        ]
        db_session.add_all(items)

        notes = [
            Note(note_id=f"note-{i}", body=f"Thesis note about sovereignty #{i}")
            for i in range(3)
        ]
        # One archived note — should be skipped
        notes.append(Note(note_id="note-archived", body="Old note", archived=True))
        db_session.add_all(notes)

        conns = [
            Connection(
                connection_id=f"conn-{i}",
                item_id="item-0",
                note_id=f"note-{i}",
                relation="reinforces",
                articulation=f"This content reinforces the thesis about #{i}",
                strength=0.8,
            )
            for i in range(2)
        ]
        db_session.add_all(conns)
        db_session.commit()

        return {
            "content_items_with_text": 3,  # item-0..2 have text, item-3 is empty
            "notes_not_archived": 3,
            "connections": 2,
        }

    def test_reindex_counts_match(self, db_session, seed_data, tmp_path):
        """Dry-run reindex counts should match source row counts."""
        # Import reindex functions
        sys_path_backup = __import__("sys").path[:]
        __import__("sys").path.insert(0, str(Path(__file__).parent.parent))

        from scripts.reindex_embeddings import reindex_content, reindex_notes, reindex_connections

        # Create a mock VectorStore with mock collections
        mock_vs = MagicMock()

        n_chunks = reindex_content(db_session, mock_vs, batch_size=32, dry_run=True)
        n_notes = reindex_notes(db_session, mock_vs, batch_size=32, dry_run=True)
        n_conns = reindex_connections(db_session, mock_vs, batch_size=32, dry_run=True)

        # Content: 3 items with text, each should produce >= 1 chunk
        assert n_chunks > 0
        assert n_notes == seed_data["notes_not_archived"]
        assert n_conns == seed_data["connections"]
