"""
InterView AI - Audio Coach.

The "Winning Feature" - Zero-latency local audio analysis.
This module analyzes HOW the candidate speaks, not WHAT they say.

Key metrics:
- Volume/RMS: Detect mumbling or speaking too quietly
- Words Per Minute (WPM): Detect rushing or dragging
- Filler Words: Count "um", "uh", "like", "you know"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import ClassVar, Optional

import numpy as np

from src.core.config import get_settings
from src.core.domain.models import CoachingFeedback, CoachingAlertLevel
from src.core.prompts import COACHING_ALERTS


logger = logging.getLogger(__name__)


class AudioCoach:
    """
    Local signal processing to analyze speaking delivery.
    
    This runs entirely on the client side with zero cloud latency,
    providing instant feedback while the candidate is still speaking.
    
    Usage:
        coach = AudioCoach()
        
        # Analyze audio chunk
        volume_alert = coach.analyze_volume(audio_numpy_array)
        
        # After transcription
        pace_alert = coach.analyze_pace(text, duration_seconds)
        filler_count = coach.get_filler_count(text)
        
        # Get combined feedback
        feedback = coach.get_coaching_feedback(text, duration, audio_data)
    """
    
    # Common filler words to detect
    FILLER_WORDS: ClassVar[list[str]] = [
        "um", "uh", "uhm", "umm",
        "like",
        "you know", "y'know",
        "actually",
        "basically",
        "literally",
        "so", "well",  # Only count at beginning of sentences
        "i mean",
        "kind of", "kinda",
        "sort of", "sorta",
    ]
    
    def __init__(self):
        self._settings = get_settings()
        self._wpm_history: list[float] = []
        self._volume_history: list[float] = []
    
    def analyze_volume(self, audio_chunk: np.ndarray) -> str:
        """
        Analyze if the user is speaking loud enough.
        
        Uses Root Mean Square (RMS) to measure volume level.
        
        Args:
            audio_chunk: Numpy array of audio samples (float32, -1 to 1)
            
        Returns:
            Status string: "OK", "📣 SPEAK UP", etc.
        """
        if audio_chunk.size == 0:
            return "OK"
        
        # Ensure float type for RMS calculation
        audio_float = audio_chunk.astype(np.float32)
        
        # Calculate RMS (root mean square) for volume
        rms = np.sqrt(np.mean(audio_float ** 2))
        self._volume_history.append(rms)
        
        # Compare against threshold
        threshold = self._settings.VOLUME_THRESHOLD
        
        if rms < threshold:
            return COACHING_ALERTS["volume_low"]
        
        return "OK"
    
    def analyze_pace(self, text: str, duration_seconds: float) -> str:
        """
        Analyze speaking pace in words per minute.
        
        Args:
            text: Transcribed text
            duration_seconds: Duration of the audio in seconds
            
        Returns:
            Status string: "OK", "🐢 SLOW DOWN", "⏩ PICK UP PACE"
        """
        if duration_seconds <= 0 or not text.strip():
            return "OK"
        
        # Count words (simple split, could be improved)
        word_count = len(text.split())
        
        # Calculate words per minute
        wpm = (word_count / duration_seconds) * 60
        self._wpm_history.append(wpm)
        
        # Check against thresholds
        if wpm > self._settings.WPM_FAST:
            return COACHING_ALERTS["pace_fast"]
        elif wpm < self._settings.WPM_SLOW:
            return COACHING_ALERTS["pace_slow"]
        
        return "OK"
    
    def get_filler_count(self, text: str) -> int:
        """
        Count filler words in the transcribed text.
        
        Args:
            text: Transcribed text
            
        Returns:
            Total count of filler words detected
        """
        if not text:
            return 0
        
        text_lower = text.lower()
        count = 0
        
        for filler in self.FILLER_WORDS:
            # Use word boundary matching for single words
            if len(filler.split()) == 1:
                # Count occurrences with word boundaries
                words = text_lower.split()
                count += words.count(filler)
            else:
                # Multi-word fillers: simple substring count
                count += text_lower.count(filler)
        
        return count
    
    def get_coaching_feedback(
        self,
        text: str,
        duration_seconds: float,
        audio_data: Optional[np.ndarray] = None,
    ) -> CoachingFeedback:
        """
        Get comprehensive coaching feedback.
        
        Combines volume, pace, and filler analysis into a single
        feedback object for the UI to display.
        
        Args:
            text: Transcribed text
            duration_seconds: Audio duration in seconds
            audio_data: Optional numpy array for volume analysis
            
        Returns:
            CoachingFeedback with all metrics
        """
        # Analyze each dimension
        volume_status = "OK"
        if audio_data is not None:
            volume_status = self.analyze_volume(audio_data)
        
        pace_status = self.analyze_pace(text, duration_seconds)
        filler_count = self.get_filler_count(text)
        
        # Calculate WPM for display
        wpm = 0.0
        if duration_seconds > 0 and text:
            wpm = (len(text.split()) / duration_seconds) * 60
        
        # Determine primary alert and level
        primary_alert = ""
        alert_level = CoachingAlertLevel.OK
        
        if volume_status != "OK":
            primary_alert = volume_status
            alert_level = CoachingAlertLevel.WARNING
        elif pace_status != "OK":
            primary_alert = pace_status
            alert_level = CoachingAlertLevel.WARNING
        elif filler_count > 5:
            primary_alert = COACHING_ALERTS["fillers_high"]
            alert_level = CoachingAlertLevel.WARNING
        elif filler_count > 10:
            alert_level = CoachingAlertLevel.CRITICAL
        else:
            primary_alert = COACHING_ALERTS["good"]
        
        return CoachingFeedback(
            volume_status=volume_status,
            pace_status=pace_status,
            filler_count=filler_count,
            words_per_minute=wpm,
            primary_alert=primary_alert,
            alert_level=alert_level,
        )
    
    def get_average_wpm(self) -> float:
        """Get average WPM across all analyzed segments."""
        if not self._wpm_history:
            return 0.0
        return sum(self._wpm_history) / len(self._wpm_history)
    
    def get_average_volume(self) -> float:
        """Get average volume (RMS) across all analyzed segments."""
        if not self._volume_history:
            return 0.0
        return sum(self._volume_history) / len(self._volume_history)
    
    def reset(self) -> None:
        """Reset all history for a new session."""
        self._wpm_history.clear()
        self._volume_history.clear()


def audio_bytes_to_numpy(audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
    """
    Convert raw audio bytes to numpy array.
    
    Supports multiple formats: WAV, WebM, MP3, etc.
    Requires ffmpeg installed for non-WAV formats.
    
    Args:
        audio_bytes: Raw audio bytes (any format supported by pydub/ffmpeg)
        sample_rate: Target sample rate for resampling
        
    Returns:
        Numpy array of float32 audio samples normalized to [-1, 1]
    """
    if not audio_bytes or len(audio_bytes) < 100:
        logger.warning("Audio bytes too small or empty")
        return np.array([], dtype=np.float32)
    
    try:
        from pydub import AudioSegment
        import io
        
        # Auto-detect format (pydub uses ffmpeg for format detection)
        # This works with WebM, WAV, MP3, OGG, etc.
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
        
        # Convert to mono if stereo
        if audio.channels > 1:
            audio = audio.set_channels(1)
        
        # Resample to target sample rate if needed
        if audio.frame_rate != sample_rate:
            audio = audio.set_frame_rate(sample_rate)
        
        # Get raw samples
        samples = np.array(audio.get_array_of_samples())
        
        if samples.size == 0:
            return np.array([], dtype=np.float32)
        
        # Normalize based on bit depth to [-1, 1] range
        max_val = float(2 ** (audio.sample_width * 8 - 1))
        normalized = samples.astype(np.float32) / max_val
        
        return normalized
        
    except Exception as e:
        logger.error(f"Error converting audio bytes: {e}")
        return np.array([], dtype=np.float32)

