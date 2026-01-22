"""
InterView AI - Domain Models.

Defines the core data structures used throughout the application.
Uses dataclasses for clarity and immutability where appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------

class InterviewState(str, Enum):
    """States in the interview state machine."""
    IDLE = "idle"
    SETUP = "setup"
    INTRO = "intro"
    QUESTIONING = "questioning"
    LISTENING = "listening"
    EVALUATING = "evaluating"
    COMPLETE = "complete"
    ERROR = "error"


class CoachingAlertLevel(str, Enum):
    """Severity levels for coaching alerts."""
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


# -----------------------------------------------------------------------------
# Coaching Models
# -----------------------------------------------------------------------------

@dataclass
class CoachingFeedback:
    """Real-time feedback from the local audio coach."""
    
    volume_status: str = "OK"
    pace_status: str = "OK"
    filler_count: int = 0
    words_per_minute: float = 0.0
    
    # Computed alert for HUD display
    primary_alert: str = ""
    alert_level: CoachingAlertLevel = CoachingAlertLevel.OK
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_status": self.volume_status,
            "pace_status": self.pace_status,
            "filler_count": self.filler_count,
            "words_per_minute": round(self.words_per_minute, 1),
            "primary_alert": self.primary_alert,
            "alert_level": self.alert_level.value,
        }


# -----------------------------------------------------------------------------
# Question & Answer Models
# -----------------------------------------------------------------------------

@dataclass
class QuestionContext:
    """Context for generating interview questions."""
    
    resume_text: str
    job_description: str
    previous_questions: list[str] = field(default_factory=list)
    previous_answers: list[str] = field(default_factory=list)
    
    def add_exchange(self, question: str, answer: str) -> None:
        """Record a Q&A exchange."""
        self.previous_questions.append(question)
        self.previous_answers.append(answer)


@dataclass
class AnswerEvaluation:
    """Evaluation of a candidate's answer."""
    
    technical_accuracy: int = 0
    clarity: int = 0
    depth: int = 0
    completeness: int = 0
    improvement_tip: str = ""
    positive_note: str = ""
    
    @property
    def average_score(self) -> float:
        """Calculate average score across all dimensions."""
        scores = [
            self.technical_accuracy,
            self.clarity,
            self.depth,
            self.completeness,
        ]
        return sum(scores) / len(scores) if scores else 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "technical_accuracy": self.technical_accuracy,
            "clarity": self.clarity,
            "depth": self.depth,
            "completeness": self.completeness,
            "average_score": round(self.average_score, 1),
            "improvement_tip": self.improvement_tip,
            "positive_note": self.positive_note,
        }


# -----------------------------------------------------------------------------
# Interview Session Models
# -----------------------------------------------------------------------------

@dataclass
class InterviewExchange:
    """Single Q&A exchange in an interview."""
    
    question: str
    answer: str
    answer_duration_seconds: float
    evaluation: AnswerEvaluation | None = None
    coaching_feedback: CoachingFeedback | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class InterviewSession:
    """Complete interview session state."""
    
    session_id: str
    state: InterviewState = InterviewState.IDLE
    
    # Context
    resume_text: str = ""
    job_description: str = ""
    
    # Interview content
    exchanges: list[InterviewExchange] = field(default_factory=list)
    current_question: str = ""
    
    # Timing
    started_at: datetime | None = None
    ended_at: datetime | None = None
    
    # Aggregate metrics
    total_questions_asked: int = 0
    total_filler_words: int = 0
    average_wpm: float = 0.0
    
    def add_exchange(self, exchange: InterviewExchange) -> None:
        """Add an exchange and update metrics."""
        self.exchanges.append(exchange)
        self.total_questions_asked = len(self.exchanges)
        
        if exchange.coaching_feedback:
            self.total_filler_words += exchange.coaching_feedback.filler_count
        
        # Update average WPM
        wpm_values = [
            ex.coaching_feedback.words_per_minute 
            for ex in self.exchanges 
            if ex.coaching_feedback
        ]
        if wpm_values:
            self.average_wpm = sum(wpm_values) / len(wpm_values)
    
    @property
    def duration_minutes(self) -> float:
        """Get session duration in minutes."""
        if not self.started_at:
            return 0.0
        end = self.ended_at or datetime.now()
        return (end - self.started_at).total_seconds() / 60
    
    @property
    def average_score(self) -> float:
        """Get average evaluation score across all answers."""
        scores = [
            ex.evaluation.average_score 
            for ex in self.exchanges 
            if ex.evaluation
        ]
        return sum(scores) / len(scores) if scores else 0.0
    
    def to_summary_dict(self) -> dict[str, Any]:
        """Generate summary for final report."""
        return {
            "session_id": self.session_id,
            "duration_minutes": round(self.duration_minutes, 1),
            "total_questions": self.total_questions_asked,
            "average_score": round(self.average_score, 1),
            "average_wpm": round(self.average_wpm, 1),
            "total_filler_words": self.total_filler_words,
        }


# -----------------------------------------------------------------------------
# Final Report Model
# -----------------------------------------------------------------------------

@dataclass 
class InterviewReport:
    """Final interview report for the candidate."""
    
    session_summary: dict[str, Any]
    overall_assessment: str
    technical_strengths: list[str]
    areas_for_improvement: list[str]
    communication_score: int
    technical_score: int
    recommendation: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "session_summary": self.session_summary,
            "overall_assessment": self.overall_assessment,
            "technical_strengths": self.technical_strengths,
            "areas_for_improvement": self.areas_for_improvement,
            "communication_score": self.communication_score,
            "technical_score": self.technical_score,
            "recommendation": self.recommendation,
        }
