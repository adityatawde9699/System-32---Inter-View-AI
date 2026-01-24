"""
InterView AI - Text-to-Speech (TTS) Adapter.

Uses pyttsx3 for local text-to-speech synthesis.
Returns audio bytes for browser playback.
"""

from __future__ import annotations

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from typing import ClassVar, Optional

from src.core.config import get_settings
from src.core.exceptions import TTSError

logger = logging.getLogger(__name__)

# Check for pyttsx3 availability
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    logger.warning("⚠️ pyttsx3 not installed. Local TTS will be disabled.")

# Check for elevenlabs availability
try:
    from elevenlabs.client import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logger.warning("⚠️ elevenlabs not installed. Premium TTS will be disabled.")


class BaseTTSEngine(ABC):
    """Abstract base class for TTS engines."""

    @abstractmethod
    def synthesize_to_bytes(self, text: str) -> Optional[bytes]:
        """Synthesize text to audio bytes."""
        pass


class TTSEngine(BaseTTSEngine):
    """
    Text-to-Speech engine using pyttsx3 (Local).
    """
    
    _engine: ClassVar[object | None] = None
    
    def __init__(self):
        if PYTTSX3_AVAILABLE and TTSEngine._engine is None:
            self._initialize_engine()
    
    def _initialize_engine(self) -> None:
        """Initialize the TTS engine with default settings."""
        try:
            TTSEngine._engine = pyttsx3.init()
            
            # Configure voice properties
            engine = TTSEngine._engine
            engine.setProperty('rate', 150)  # Speed (words per minute)
            engine.setProperty('volume', 0.9)  # Volume (0.0 to 1.0)
            
            # Try to set a natural-sounding voice
            voices = engine.getProperty('voices')
            if voices:
                # Prefer a female voice for variety (usually index 1)
                voice_index = 1 if len(voices) > 1 else 0
                engine.setProperty('voice', voices[voice_index].id)
            
            logger.info("✅ Local TTS engine initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Local TTS: {e}")
            TTSEngine._engine = None
    
    def synthesize_to_bytes(self, text: str) -> Optional[bytes]:
        """Synthesize text to WAV audio bytes."""
        if not PYTTSX3_AVAILABLE or TTSEngine._engine is None:
            return None
        
        if not text.strip():
            return None
        
        temp_path = tempfile.mktemp(suffix=".wav")
        try:
            # Note: pyttsx3 is not thread-safe for synthesis to file usually
            # But we wrap it in create_orchestrator loops
            engine = TTSEngine._engine
            engine.save_to_file(text, temp_path)
            engine.runAndWait()
            
            with open(temp_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Local TTS synthesis error: {e}")
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class ElevenLabsTTSEngine(BaseTTSEngine):
    """
    Text-to-Speech engine using ElevenLabs (Cloud).
    """

    def __init__(self, api_key: str, voice_id: str):
        self._api_key = api_key
        self._voice_id = voice_id
        if ELEVENLABS_AVAILABLE and api_key:
            try:
                self._client = ElevenLabs(api_key=api_key)
                logger.info("✅ ElevenLabs TTS engine initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize ElevenLabs TTS: {e}")
                self._client = None
        else:
            self._client = None

    def synthesize_to_bytes(self, text: str) -> Optional[bytes]:
        """Synthesize text to MP3 audio bytes."""
        if not self._client or not text.strip():
            return None

        try:
            audio_gen = self._client.text_to_speech.convert(
                text=text,
                voice_id=self._voice_id,
                model_id="eleven_multilingual_v2"
            )
            # Collect bytes from generator
            return b"".join(audio_gen)
        except Exception as e:
            logger.error(f"ElevenLabs TTS synthesis error: {str(e)}")
            return None


def get_tts_engine() -> BaseTTSEngine:
    """
    Factory function to get the configured TTS engine.
    
    Returns ElevenLabs engine if configured and available, 
    otherwise falls back to local pyttsx3 engine.
    """
    settings = get_settings()
    
    # Try ElevenLabs first if enabled and key is present
    if settings.TTS_ENGINE == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        if ELEVENLABS_AVAILABLE:
            engine = ElevenLabsTTSEngine(
                settings.ELEVENLABS_API_KEY, 
                settings.ELEVENLABS_VOICE_ID
            )
            # Test if initialized correctly
            if engine._client:
                return engine
        logger.warning("ElevenLabs requested but unavailable or failed to init. Falling back to local TTS.")
    
    # Fallback to local
    return TTSEngine()
