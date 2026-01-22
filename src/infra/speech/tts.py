"""
InterView AI - Text-to-Speech (TTS) Adapter.

Uses pyttsx3 for local text-to-speech synthesis.
Returns audio bytes for browser playback.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import ClassVar, Optional

from src.core.exceptions import TTSError


logger = logging.getLogger(__name__)


# Check for pyttsx3 availability
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    logger.warning("⚠️ pyttsx3 not installed. TTS will be disabled.")


class TTSEngine:
    """
    Text-to-Speech engine using pyttsx3.
    
    Provides methods to:
    - Synthesize text to audio bytes (for browser playback)
    - Speak directly (for local testing)
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
            
            logger.info("✅ TTS engine initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize TTS: {e}")
            TTSEngine._engine = None
    
    def synthesize_to_bytes(self, text: str) -> Optional[bytes]:
        """
        Synthesize text to audio bytes.
        
        Args:
            text: Text to synthesize
            
        Returns:
            WAV audio bytes, or None if synthesis fails
        """
        if not PYTTSX3_AVAILABLE or TTSEngine._engine is None:
            logger.warning("TTS unavailable, returning None")
            return None
        
        if not text.strip():
            return None
        
        # Create temp file for audio output
        temp_path = tempfile.mktemp(suffix=".wav")
        
        try:
            engine = TTSEngine._engine
            engine.save_to_file(text, temp_path)
            engine.runAndWait()
            
            # Read the generated audio
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            
            logger.debug(f"Synthesized {len(text)} chars to {len(audio_bytes)} bytes")
            return audio_bytes
            
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            raise TTSError(f"Failed to synthesize speech: {e}")
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def speak(self, text: str) -> None:
        """
        Speak text directly (blocking).
        
        Useful for local testing.
        
        Args:
            text: Text to speak
        """
        if not PYTTSX3_AVAILABLE or TTSEngine._engine is None:
            logger.warning("TTS unavailable, cannot speak")
            return
        
        if not text.strip():
            return
        
        try:
            engine = TTSEngine._engine
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.error(f"TTS speak error: {e}")
    
    def set_rate(self, words_per_minute: int) -> None:
        """Set speech rate."""
        if TTSEngine._engine:
            TTSEngine._engine.setProperty('rate', words_per_minute)
    
    def set_volume(self, volume: float) -> None:
        """Set speech volume (0.0 to 1.0)."""
        if TTSEngine._engine:
            TTSEngine._engine.setProperty('volume', max(0.0, min(1.0, volume)))
    
    @classmethod
    def reset(cls) -> None:
        """Reset the TTS engine (useful for testing)."""
        if cls._engine:
            try:
                cls._engine.stop()
            except Exception:
                pass
        cls._engine = None
