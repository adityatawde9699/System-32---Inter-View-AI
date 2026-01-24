"""
InterView AI - Configuration Management.

Uses pydantic-settings for environment variable loading with validation.
"""

import logging
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    # -------------------------------------------------------------------------
    # API Keys
    # -------------------------------------------------------------------------
    GEMINI_API_KEY: str = ""
    
    # -------------------------------------------------------------------------
    # Firebase Configuration
    # -------------------------------------------------------------------------
    # Path to your Firebase Admin SDK service account JSON file
    FIREBASE_CREDENTIALS_PATH: str = "firebase_credentials.json"
    
    # -------------------------------------------------------------------------
    # Whisper STT Configuration
    # -------------------------------------------------------------------------
    WHISPER_MODEL: Literal["tiny", "base", "small", "medium", "large"] = "tiny"
    WHISPER_DEVICE: Literal["cpu", "cuda", "auto"] = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    
    # -------------------------------------------------------------------------
    # Audio Coaching Thresholds
    # -------------------------------------------------------------------------
    VOLUME_THRESHOLD: float = 0.02  # RMS threshold for "speak up" alert
    WPM_FAST: int = 160  # Words per minute threshold for "slow down"
    WPM_SLOW: int = 100  # Words per minute threshold for "speed up"
    
    # -------------------------------------------------------------------------
    # Interview Configuration
    # -------------------------------------------------------------------------
    INTERVIEW_DURATION_MINUTES: int = 15
    MAX_QUESTIONS: int = 10
    QUESTION_TIMEOUT_SECONDS: int = 120
    
    # -------------------------------------------------------------------------
    # Application Settings
    # -------------------------------------------------------------------------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    DEBUG_MODE: bool = False
    
    # -------------------------------------------------------------------------
    # Paths
    # -------------------------------------------------------------------------
    RESUME_UPLOAD_DIR: str = "data/resumes"
    SESSION_LOG_DIR: str = "data/session_logs"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def configure_logging() -> None:
    """Configure application logging based on settings."""
    settings = get_settings()
    
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format=log_format,
        datefmt=date_format,
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)