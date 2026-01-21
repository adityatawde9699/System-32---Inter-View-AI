"""
InterView AI - Speech-to-Text (STT) Adapter.

Uses faster-whisper for local transcription.
Implements singleton pattern for model loading to prevent repeated initialization.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, ClassVar, Optional

from src.core.config import get_settings
from src.core.exceptions import TranscriptionError


logger = logging.getLogger(__name__)


# Check for faster_whisper availability
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("⚠️ faster-whisper not installed. STT will use mock fallback.")


class WhisperSTT:
    """
    Speech-to-Text adapter using faster-whisper.
    
    Uses a class-level cache to load the Whisper model only once,
    preventing the expensive model initialization on every request.
    """
    
    _model_cache: ClassVar[Optional[Any]] = None
    _model_loaded: ClassVar[bool] = False
    
    def __init__(self):
        self._settings = get_settings()
        
        # Initialize model if available and not already loaded
        if WHISPER_AVAILABLE and not WhisperSTT._model_loaded:
            self._initialize_model()
    
    def _initialize_model(self) -> None:
        """Load the Whisper model into the class cache."""
        logger.info(f"⏳ Loading Whisper model ({self._settings.WHISPER_MODEL})...")
        
        try:
            device = self._settings.WHISPER_DEVICE
            if device == "auto":
                device = "cuda" if self._cuda_available() else "cpu"
            
            WhisperSTT._model_cache = WhisperModel(
                self._settings.WHISPER_MODEL,
                device=device,
                compute_type=self._settings.WHISPER_COMPUTE_TYPE,
            )
            WhisperSTT._model_loaded = True
            logger.info(f"✅ Whisper model loaded on {device}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load Whisper model: {e}")
            WhisperSTT._model_cache = None
            WhisperSTT._model_loaded = False
    
    def _cuda_available(self) -> bool:
        """Check if CUDA is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)
            
        Returns:
            Transcribed text
            
        Raises:
            TranscriptionError: If transcription fails
        """
        # Validate file exists
        if not os.path.exists(audio_path):
            raise TranscriptionError(f"Audio file not found: {audio_path}")
        
        # Fallback if Whisper unavailable
        if not WHISPER_AVAILABLE or WhisperSTT._model_cache is None:
            logger.warning("🎤 [Fallback] Using mock transcription")
            return self._mock_transcription()
        
        try:
            segments, info = WhisperSTT._model_cache.transcribe(
                audio_path,
                beam_size=5,
                language="en",
                vad_filter=True,  # Filter out silence
            )
            
            # Combine all segments
            text = " ".join(segment.text for segment in segments).strip()
            
            logger.debug(f"Transcribed {info.duration:.1f}s audio: {text[:50]}...")
            return text
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            raise TranscriptionError(str(e))
    
    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe audio from bytes.
        
        Args:
            audio_bytes: Raw audio bytes (WAV format)
            sample_rate: Audio sample rate
            
        Returns:
            Transcribed text
        """
        # Write to temp file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(audio_bytes)
            temp_path = f.name
        
        try:
            return self.transcribe(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def _mock_transcription(self) -> str:
        """Return mock transcription for testing without Whisper."""
        return (
            "I worked on a Python backend project where we used Flask "
            "and PostgreSQL to build a REST API. The main challenge was "
            "handling concurrent database connections efficiently."
        )
    
    @classmethod
    def reset_model(cls) -> None:
        """Reset the model cache (useful for testing)."""
        cls._model_cache = None
        cls._model_loaded = False


def get_audio_duration(audio_path: str) -> float:
    """
    Get duration of audio file in seconds.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Duration in seconds
    """
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        return len(audio) / 1000.0  # pydub uses milliseconds
    except Exception:
        return 0.0
