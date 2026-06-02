"""
Ten31 Thoughts - Chunked Audio Transcriber
Handles large podcast files by splitting with ffmpeg and transcribing chunks.
Alternative to pydub-based chunking - uses ffmpeg directly (lighter dependency).
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

CHUNK_DURATION_SECONDS = 1200  # 20 minutes per chunk
MAX_CHUNKS = 20  # Safety limit - 20 chunks × 20 min = 6.7 hours max


async def split_audio_ffmpeg(audio_file: Path, output_dir: Path) -> List[Path]:
    """
    Split audio file into chunks using ffmpeg.
    
    Args:
        audio_file: Path to input audio file
        output_dir: Directory to write chunks to
        
    Returns:
        List of chunk file paths created
    """
    try:
        chunk_files = []
        chunk_index = 0

        logger.info(f"Splitting {audio_file} into {CHUNK_DURATION_SECONDS}s chunks")

        while chunk_index < MAX_CHUNKS:
            start_time = chunk_index * CHUNK_DURATION_SECONDS
            output_file = output_dir / f"chunk_{chunk_index:03d}.mp3"
            
            cmd = [
                "ffmpeg", "-y",  # -y to overwrite existing files
                "-i", str(audio_file),
                "-ss", str(start_time),  # start time in seconds
                "-t", str(CHUNK_DURATION_SECONDS),  # duration in seconds
                "-acodec", "mp3",
                "-ar", "16000",  # 16kHz sample rate (optimal for speech recognition)
                "-ac", "1",  # mono
                "-ab", "64k",  # 64kbps bitrate (sufficient for speech)
                str(output_file)
            ]

            logger.debug(f"Running: {' '.join(cmd)}")
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 min timeout per chunk
                )
            except subprocess.TimeoutExpired:
                logger.error(f"ffmpeg timeout for chunk {chunk_index}")
                break

            if result.returncode != 0:
                logger.debug(f"ffmpeg exit code {result.returncode} for chunk {chunk_index}: {result.stderr}")
                # Non-zero exit is normal when we've reached end of audio
                break

            # Check if output file was created and has meaningful content
            if output_file.exists() and output_file.stat().st_size > 1024:  # > 1KB
                chunk_files.append(output_file)
                chunk_index += 1
                logger.debug(f"Created chunk {chunk_index}: {output_file.stat().st_size} bytes")
            else:
                # No output or tiny file - we've reached the end
                logger.debug(f"No substantial output for chunk {chunk_index}, stopping")
                if output_file.exists():
                    output_file.unlink()  # Clean up empty file
                break

        if chunk_files:
            total_size = sum(f.stat().st_size for f in chunk_files)
            logger.info(f"Split into {len(chunk_files)} chunks, total: {total_size / 1024 / 1024:.1f} MB")
        else:
            logger.warning("No chunks created - check input file format")

        return chunk_files

    except Exception as e:
        logger.error(f"Audio splitting failed: {e}")
        return []


def cleanup_chunks(chunk_files: List[Path]) -> None:
    """Clean up temporary chunk files."""
    for chunk_file in chunk_files:
        try:
            if chunk_file.exists():
                chunk_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to cleanup {chunk_file}: {e}")


async def transcribe_chunked_audio(
    audio_file: Path,
    transcribe_function,
    temp_dir: Optional[Path] = None
) -> Optional[str]:
    """
    Transcribe a large audio file by chunking it.
    
    Args:
        audio_file: Path to the audio file to transcribe
        transcribe_function: Async function that takes a file path and returns transcript text
        temp_dir: Optional temp directory (will create one if not provided)
        
    Returns:
        Combined transcript or None if failed
    """
    created_temp_dir = False
    if temp_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ten31_chunks_"))
        created_temp_dir = True

    try:
        # Split audio into chunks
        chunk_files = await split_audio_ffmpeg(audio_file, temp_dir)
        
        if not chunk_files:
            logger.error("Failed to create any audio chunks")
            return None

        logger.info(f"Transcribing {len(chunk_files)} chunks")

        # Transcribe each chunk
        transcripts = []
        failed_chunks = 0
        
        for i, chunk_file in enumerate(chunk_files, 1):
            try:
                logger.info(f"Transcribing chunk {i}/{len(chunk_files)}")
                transcript = await transcribe_function(chunk_file)
                
                if transcript and transcript.strip():
                    transcripts.append(f"[Segment {i}]\n\n{transcript.strip()}")
                else:
                    logger.warning(f"Empty transcript for chunk {i}")
                    failed_chunks += 1
                    
            except Exception as e:
                logger.error(f"Failed to transcribe chunk {i}: {e}")
                failed_chunks += 1

        # Clean up chunks
        cleanup_chunks(chunk_files)

        if not transcripts:
            logger.error("No successful chunk transcriptions")
            return None

        if failed_chunks > 0:
            logger.warning(f"{failed_chunks}/{len(chunk_files)} chunks failed transcription")

        # Combine transcripts with segment markers
        full_transcript = "\n\n".join(transcripts)
        
        logger.info(
            f"Chunked transcription complete: {len(transcripts)} successful segments, "
            f"{len(full_transcript)} total characters"
        )
        
        return full_transcript

    except Exception as e:
        logger.error(f"Chunked transcription failed: {e}")
        return None
        
    finally:
        # Clean up temp directory if we created it
        if created_temp_dir and temp_dir.exists():
            try:
                temp_dir.rmdir()  # Only removes if empty
            except OSError:
                pass  # Directory not empty, leave it


# Test function for standalone use
async def test_chunking():
    """Test the chunking functionality with a sample file."""
    import asyncio
    
    # Mock transcriber function
    async def mock_transcriber(file_path: Path) -> str:
        await asyncio.sleep(0.1)  # Simulate processing time
        return f"Mock transcript for {file_path.name}"
    
    # This would normally be a real audio file
    test_file = Path("/tmp/test_audio.mp3")
    
    if test_file.exists():
        result = await transcribe_chunked_audio(test_file, mock_transcriber)
        print(f"Result: {result[:200]}..." if result else "Failed")
    else:
        print("Test audio file not found")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_chunking())