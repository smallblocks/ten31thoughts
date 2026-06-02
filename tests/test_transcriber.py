"""
Tests for the PodcastTranscriber module.
"""

import json
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
from datetime import datetime, timezone

from src.feeds.transcriber import PodcastTranscriber, _get_whisper_config, STORE_JSON_PATH
from src.db.models import ContentItem, AnalysisStatus


class TestWhisperConfig:
    """Test Whisper configuration loading."""

    def test_get_whisper_config_missing_file(self):
        """Test config loading when store.json doesn't exist."""
        with patch.object(
            Path, "read_text", side_effect=FileNotFoundError("no file")
        ):
            config = _get_whisper_config()
            assert config == {}

    def test_get_whisper_config_invalid_json(self):
        """Test config loading when store.json is corrupt."""
        with patch.object(Path, "read_text", return_value="not json{{{"):
            config = _get_whisper_config()
            assert config == {}

    def test_get_whisper_config_valid(self):
        """Test config loading with valid store.json."""
        store_data = json.dumps({
            "whisperUrl": "http://192.168.86.52:8000",
            "whisperApi": "openai",
            "whisperModel": "whisper-large-v3",
        })
        with patch.object(Path, "read_text", return_value=store_data):
            config = _get_whisper_config()
            assert config["url"] == "http://192.168.86.52:8000"
            assert config["api"] == "openai"
            assert config["model"] == "whisper-large-v3"

    def test_get_whisper_config_defaults(self):
        """Test defaults when keys are missing from store.json."""
        with patch.object(Path, "read_text", return_value="{}"):
            config = _get_whisper_config()
            assert config["url"] == ""
            assert config["api"] == "openai"
            assert config["model"] == "whisper-large-v3"


class TestPodcastTranscriber:
    """Test the PodcastTranscriber class."""

    @pytest.fixture
    def mock_session(self):
        return Mock()

    @pytest.fixture
    def transcriber(self, mock_session):
        with patch("src.feeds.transcriber._get_whisper_config") as mock_cfg:
            mock_cfg.return_value = {
                "url": "http://localhost:8000",
                "api": "openai",
                "model": "whisper-large-v3",
            }
            return PodcastTranscriber(mock_session)

    @pytest.fixture
    def audio_item(self):
        return ContentItem(
            item_id="test_item",
            feed_id="test_feed",
            url="https://example.com/podcast",
            title="Test Podcast Episode",
            content_type="audio",
            audio_url="https://example.com/audio.mp3",
            analysis_status=AnalysisStatus.PENDING,
            content_text="",
        )

    # ── can_transcribe ──

    def test_can_transcribe_true(self, transcriber):
        assert transcriber.can_transcribe() is True

    def test_can_transcribe_false(self, mock_session):
        with patch("src.feeds.transcriber._get_whisper_config") as mock_cfg:
            mock_cfg.return_value = {"url": "", "api": "openai", "model": "whisper-large-v3"}
            t = PodcastTranscriber(mock_session)
            assert t.can_transcribe() is False

    # ── get_transcribable_items ──

    def test_get_transcribable_items_empty(self, transcriber):
        transcriber.session.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        assert transcriber.get_transcribable_items() == []

    # ── transcribe guards ──

    @pytest.mark.asyncio
    async def test_transcribe_no_whisper_config(self, mock_session):
        with patch("src.feeds.transcriber._get_whisper_config") as mock_cfg:
            mock_cfg.return_value = {"url": "", "api": "openai", "model": ""}
            t = PodcastTranscriber(mock_session)
            item = ContentItem(audio_url="https://example.com/audio.mp3", content_text="")
            assert await t.transcribe(item) is False

    @pytest.mark.asyncio
    async def test_transcribe_no_audio_url(self, transcriber):
        item = ContentItem(audio_url=None, content_text="")
        assert await transcriber.transcribe(item) is False

    @pytest.mark.asyncio
    async def test_transcribe_already_has_content(self, transcriber):
        item = ContentItem(
            audio_url="https://example.com/audio.mp3",
            content_text="x" * 300,
        )
        assert await transcriber.transcribe(item) is True  # treated as already done

    # ── transcription paths ──

    @pytest.mark.asyncio
    async def test_transcribe_small_file(self, transcriber, audio_item, mock_session):
        """Small file goes through _transcribe_file (no chunking)."""
        fake_path = MagicMock(spec=Path)
        fake_path.stat.return_value.st_size = 5_000_000  # 5 MB
        fake_path.exists.return_value = True

        transcriber._download_audio = AsyncMock(return_value=fake_path)
        transcriber._transcribe_file = AsyncMock(return_value="Hello world transcript")

        result = await transcriber.transcribe(audio_item)

        assert result is True
        assert audio_item.content_text == "Hello world transcript"
        assert audio_item.content_type == "podcast_transcript"
        mock_session.commit.assert_called_once()
        transcriber._transcribe_file.assert_awaited_once_with(fake_path)

    @pytest.mark.asyncio
    async def test_transcribe_large_file_uses_chunking(self, transcriber, audio_item, mock_session):
        """Files > 25 MB go through _transcribe_chunked."""
        fake_path = MagicMock(spec=Path)
        fake_path.stat.return_value.st_size = 30 * 1024 * 1024  # 30 MB
        fake_path.exists.return_value = True

        transcriber._download_audio = AsyncMock(return_value=fake_path)
        transcriber._transcribe_chunked = AsyncMock(return_value="chunked transcript")

        result = await transcriber.transcribe(audio_item)

        assert result is True
        transcriber._transcribe_chunked.assert_awaited_once_with(fake_path)

    @pytest.mark.asyncio
    async def test_transcribe_oversized_file_rejected(self, transcriber, audio_item):
        """Files > 500 MB are rejected."""
        fake_path = MagicMock(spec=Path)
        fake_path.stat.return_value.st_size = 600 * 1024 * 1024
        fake_path.exists.return_value = True

        transcriber._download_audio = AsyncMock(return_value=fake_path)

        result = await transcriber.transcribe(audio_item)
        assert result is False

    @pytest.mark.asyncio
    async def test_transcribe_download_failure(self, transcriber, audio_item):
        """Download failure returns False without crashing."""
        transcriber._download_audio = AsyncMock(return_value=None)
        assert await transcriber.transcribe(audio_item) is False

    @pytest.mark.asyncio
    async def test_transcribe_empty_transcript(self, transcriber, audio_item, mock_session):
        """Empty Whisper response returns False."""
        fake_path = MagicMock(spec=Path)
        fake_path.stat.return_value.st_size = 5_000_000
        fake_path.exists.return_value = True

        transcriber._download_audio = AsyncMock(return_value=fake_path)
        transcriber._transcribe_file = AsyncMock(return_value="")

        result = await transcriber.transcribe(audio_item)
        assert result is False
        mock_session.commit.assert_not_called()


class TestChunkedTranscriber:
    """Test the chunked audio transcriber (ffmpeg splitting)."""

    @pytest.mark.asyncio
    async def test_transcribe_chunked_audio_concatenation(self):
        """Test that chunk transcripts are concatenated with segment markers."""
        from src.feeds.chunked_transcriber import transcribe_chunked_audio

        chunk_paths = [Path(f"/tmp/chunk_{i}.mp3") for i in range(3)]

        async def mock_transcribe(path: Path) -> str:
            idx = chunk_paths.index(path)
            return f"Transcript for segment {idx + 1}"

        with patch(
            "src.feeds.chunked_transcriber.split_audio_ffmpeg",
            new_callable=AsyncMock,
            return_value=chunk_paths,
        ), patch(
            "src.feeds.chunked_transcriber.cleanup_chunks",
        ):
            result = await transcribe_chunked_audio(
                Path("/tmp/test.mp3"), mock_transcribe
            )

        assert result is not None
        assert "[Segment 1]" in result
        assert "[Segment 2]" in result
        assert "[Segment 3]" in result
        assert "Transcript for segment 1" in result

    @pytest.mark.asyncio
    async def test_transcribe_chunked_audio_no_chunks(self):
        """Empty chunk list returns None."""
        from src.feeds.chunked_transcriber import transcribe_chunked_audio

        with patch(
            "src.feeds.chunked_transcriber.split_audio_ffmpeg",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await transcribe_chunked_audio(
                Path("/tmp/test.mp3"), AsyncMock()
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_split_audio_ffmpeg_calls(self):
        """Verify ffmpeg is called correctly for each chunk."""
        from src.feeds.chunked_transcriber import split_audio_ffmpeg

        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            m = Mock()
            # First 2 calls succeed, third fails (end of audio)
            m.returncode = 0 if call_count <= 2 else 1
            m.stderr = ""
            return m

        with patch("subprocess.run", side_effect=mock_run), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.stat") as mock_stat, \
             patch("pathlib.Path.unlink"):
            mock_stat.return_value.st_size = 5_000_000  # 5 MB per chunk

            output_dir = Path("/tmp/chunks_test")
            chunks = await split_audio_ffmpeg(Path("/tmp/test.mp3"), output_dir)

            assert len(chunks) == 2
            assert call_count == 3  # 2 successful + 1 end sentinel


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
