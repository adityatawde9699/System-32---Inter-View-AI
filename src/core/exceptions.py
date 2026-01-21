"""
InterView AI - Custom Exceptions.

Defines a hierarchy of domain-specific exceptions for clean error handling.
"""

from __future__ import annotations
from typing import Optional


class InterviewAIError(Exception):
    """Base exception for all InterView AI errors."""
    
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


# -----------------------------------------------------------------------------
# Configuration Errors
# -----------------------------------------------------------------------------

class ConfigurationError(InterviewAIError):
    """Raised when configuration is invalid or missing."""
    pass


class MissingAPIKeyError(ConfigurationError):
    """Raised when a required API key is missing."""
    
    def __init__(self, key_name: str):
        super().__init__(
            message=f"Missing required API key: {key_name}",
            details="Please set this in your .env file or environment variables",
        )


# -----------------------------------------------------------------------------
# LLM Errors
# -----------------------------------------------------------------------------

class LLMError(InterviewAIError):
    """Base exception for LLM-related errors."""
    pass


class LLMConnectionError(LLMError):
    """Raised when unable to connect to the LLM service."""
    
    def __init__(self, service: str, reason: str):
        super().__init__(
            message=f"Failed to connect to {service}",
            details=reason,
        )


class LLMRateLimitError(LLMError):
    """Raised when rate limited by the LLM service."""
    
    def __init__(self, service: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(
            message=f"Rate limited by {service}",
            details=f"Retry after {retry_after}s" if retry_after else None,
        )


class LLMResponseError(LLMError):
    """Raised when the LLM returns an invalid or blocked response."""
    pass


# -----------------------------------------------------------------------------
# Speech Errors
# -----------------------------------------------------------------------------

class SpeechError(InterviewAIError):
    """Base exception for speech processing errors."""
    pass


class TranscriptionError(SpeechError):
    """Raised when audio transcription fails."""
    pass


class TTSError(SpeechError):
    """Raised when text-to-speech synthesis fails."""
    pass


# -----------------------------------------------------------------------------
# Document Errors
# -----------------------------------------------------------------------------

class DocumentError(InterviewAIError):
    """Base exception for document processing errors."""
    pass


class PDFParseError(DocumentError):
    """Raised when PDF parsing fails."""
    
    def __init__(self, filename: str, reason: str):
        super().__init__(
            message=f"Failed to parse PDF: {filename}",
            details=reason,
        )


class EmptyDocumentError(DocumentError):
    """Raised when a document has no extractable content."""
    pass


# -----------------------------------------------------------------------------
# Interview Session Errors
# -----------------------------------------------------------------------------

class SessionError(InterviewAIError):
    """Base exception for interview session errors."""
    pass


class SessionNotFoundError(SessionError):
    """Raised when a session ID is not found."""
    
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session not found: {session_id}",
        )


class SessionExpiredError(SessionError):
    """Raised when a session has expired."""
    pass


class InvalidSessionStateError(SessionError):
    """Raised when an operation is invalid for the current session state."""
    
    def __init__(self, current_state: str, required_state: str):
        super().__init__(
            message=f"Invalid session state",
            details=f"Current: {current_state}, Required: {required_state}",
        )
