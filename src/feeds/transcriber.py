"""
Ten31 Thoughts - Podcast Transcriber
Downloads audio from ContentItems and transcribes via Whisper.
Handles large podcast files with chunking support.
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..db.models import ContentItem, AnalysisStatus

logger = logging.getLogger(__name__)

# Store JSON path for Whisper configuration
STORE_JSON_PATH = Path("/data/store.json")

# File size limits
MAX_AUDIO_SIZE = 500 * 1024 * 1024  # 500 MB absolute max
CHUNK_SIZE_THRESHOLD = 25 * 1024 * 1024  # 25 MB - split larger files


def _get_whisper_config() -> dict:
    """Read Whisper config from /data/store.json."""
    try:
        data = json.loads(STORE_JSON_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {
        "url": data.get("whisperUrl", ""),
        "api": data.get("whisperApi", "openai"),
        "model": data.get("whisperModel", "whisper-large-v3"),
    }


class PodcastTranscriber:
    """
    Transcribes podcast audio from ContentItems.
    
    Workflow:
    1. Download audio from item.audio_url
    2. Check size - if > 25MB, chunk with ffmpeg
    3. Send chunks to Whisper server
    4. Concatenate transcripts
    5. Update item.content_text and mark as pending analysis
    """

    def __init__(self, session: Session, timeout: int = 1800):  # 30 min default timeout
        self.session = session
        self.timeout = timeout
        self.whisper_config = _get_whisper_config()

    def can_transcribe(self) -> bool:
        """Check if Whisper is configured and available."""
        return bool(self.whisper_config.get("url", "").strip())

    async def transcribe(self, item: ContentItem) -> bool:
        """
        Transcribe a ContentItem's audio.
        
        Args:
            item: ContentItem with audio_url set
            
        Returns:
            True if transcription succeeded, False otherwise
        """
        if not self.can_transcribe():
            logger.warning("Whisper not configured - skipping transcription")
            return False

        if not item.audio_url:
            logger.warning(f"No audio_url for item {item.item_id}")
            return False

        # Skip if already transcribed (content_text has substantial content)
        if item.content_text and len(item.content_text.strip()) > 200:
            logger.info(f"Item {item.item_id} already has content, skipping transcription")
            return True

        logger.info(f"Starting transcription for {item.title} ({item.item_id})")
        
        try:
            # Download audio to temp file
            audio_file = await self._download_audio(item.audio_url)
            if not audio_file:
                return False

            try:
                # Get file size
                file_size = audio_file.stat().st_size
                logger.info(f"Downloaded audio: {file_size / 1024 / 1024:.1f} MB")

                if file_size > MAX_AUDIO_SIZE:
                    logger.error(f"Audio file too large: {file_size / 1024 / 1024:.1f} MB > {MAX_AUDIO_SIZE / 1024 / 1024} MB")
                    return False

                # Transcribe (with chunking if needed)
                if file_size > CHUNK_SIZE_THRESHOLD:
                    transcript = await self._transcribe_chunked(audio_file)
                else:
                    transcript = await self._transcribe_file(audio_file)

                if not transcript:
                    logger.error(f"Empty transcript for {item.item_id}")
                    return False

                # Update the item
                item.content_text = transcript
                item.content_type = "podcast_transcript"
                # Keep analysis_status as PENDING so it gets picked up by analysis
                
                self.session.commit()
                
                logger.info(f"Transcription complete: {len(transcript)} chars for {item.title}")
                return True

            finally:
                # Clean up temp file
                if audio_file.exists():
                    audio_file.unlink()

        except Exception as e:
            logger.error(f"Transcription failed for {item.item_id}: {e}")
            return False

    async def _download_audio(self, audio_url: str) -> Optional[Path]:
        """Download audio file to a temporary location (streamed to avoid memory pressure)."""
        try:
            logger.info(f"Downloading audio from {audio_url}")

            # Determine extension from URL
            suffix = ".mp3"  # Default
            if "m4a" in audio_url.lower():
                suffix = ".m4a"
            elif "mp4" in audio_url.lower():
                suffix = ".m4a"
            elif "wav" in audio_url.lower():
                suffix = ".wav"
            elif "ogg" in audio_url.lower():
                suffix = ".ogg"

            temp_file = Path(tempfile.mktemp(suffix=suffix))
            total_bytes = 0

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, read=300.0),  # 5 min read timeout
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", audio_url) as response:
                    response.raise_for_status()
                    with open(temp_file, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            total_bytes += len(chunk)
                            if total_bytes > MAX_AUDIO_SIZE:
                                logger.error(f"Download aborted: exceeds {MAX_AUDIO_SIZE / 1024 / 1024:.0f} MB")
                                temp_file.unlink(missing_ok=True)
                                return None

            logger.info(f"Downloaded {total_bytes / 1024 / 1024:.1f} MB to {temp_file}")
            return temp_file

        except Exception as e:
            logger.error(f"Failed to download audio from {audio_url}: {e}")
            return None

    async def _transcribe_file(self, audio_file: Path) -> Optional[str]:
        """Transcribe a single audio file via Whisper."""
        whisper_url = self.whisper_config["url"].rstrip("/")
        whisper_api = self.whisper_config["api"]
        whisper_model = self.whisper_config["model"]

        file_size = audio_file.stat().st_size

        try:
            # Stream file from disk instead of reading all into memory
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, read=float(self.timeout)),
            ) as client:
                if whisper_api == "whisper-cpp":
                    url = f"{whisper_url}/inference"
                    files = {"file": (audio_file.name, open(audio_file, "rb"), "audio/mpeg")}
                    data = {"temperature": "0.0", "response_format": "json"}
                else:
                    url = f"{whisper_url}/v1/audio/transcriptions"
                    files = {"file": (audio_file.name, open(audio_file, "rb"), "audio/mpeg")}
                    data = {"model": whisper_model, "response_format": "json"}

                logger.info(f"Sending {file_size / 1024 / 1024:.1f} MB to Whisper at {url}")
                response = await client.post(url, files=files, data=data)
                response.raise_for_status()

                result = response.json()
                transcript = result.get("text", "").strip()

                logger.info(f"Whisper returned {len(transcript)} characters")
                return transcript

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return None

    async def _transcribe_chunked(self, audio_file: Path) -> Optional[str]:
        """Transcribe a large audio file by splitting into chunks."""
        logger.info(f"File size exceeds {CHUNK_SIZE_THRESHOLD / 1024 / 1024:.1f} MB, chunking...")

        try:
            from .chunked_transcriber import transcribe_chunked_audio
            
            # Use the dedicated chunked transcriber
            result = await transcribe_chunked_audio(audio_file, self._transcribe_file)
            return result

        except Exception as e:
            logger.error(f"Chunked transcription failed: {e}")
            return None



    async def transcribe_item(self, item_id: str) -> bool:
        """Transcribe a specific ContentItem by ID."""
        item = self.session.get(ContentItem, item_id)
        if not item:
            logger.warning(f"ContentItem {item_id} not found")
            return False

        return await self.transcribe(item)

    def get_transcribable_items(self, limit: int = 3) -> list[ContentItem]:
        """
        Get ContentItems that need transcription.
        
        Criteria:
        - content_type == 'audio'
        - (content_text is NULL or empty or < 200 chars)
        - analysis_status == 'pending'
        """
        from sqlalchemy import and_, func, or_

        items = self.session.query(ContentItem).filter(
            and_(
                ContentItem.content_type == "audio",
                or_(
                    ContentItem.content_text.is_(None),
                    ContentItem.content_text == "",
                    func.length(ContentItem.content_text) < 200
                ),
                ContentItem.analysis_status == AnalysisStatus.PENDING
            )
        ).limit(limit).all()

        return items