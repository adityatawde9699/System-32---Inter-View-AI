"""
InterView AI - Interview Orchestrator.

Manages the interview state machine and coordinates all components:
- LLM (Gemini) for question generation
- STT (Whisper) for transcription
- TTS (pyttsx3) for voice output
- AudioCoach for real-time feedback

State Flow:
IDLE -> SETUP -> INTRO -> QUESTIONING <-> LISTENING -> EVALUATING -> COMPLETE
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Callable, Optional

from src.core.config import get_settings
from src.core.domain.models import (
    InterviewState,
    InterviewSession,
    InterviewExchange,
    QuestionContext,
    AnswerEvaluation,
    CoachingFeedback,
)
from src.core.exceptions import (
    InvalidSessionStateError,
    SessionError,
)
from src.infra.llm.gemini import GeminiInterviewer
from src.infra.speech.stt import WhisperSTT, get_audio_duration
from src.infra.speech.tts import TTSEngine
from src.app.coaching import AudioCoach, audio_bytes_to_numpy


logger = logging.getLogger(__name__)


class InterviewOrchestrator:
    """
    Main orchestrator for the interview flow.
    
    Manages the interview state machine and coordinates
    all AI components to provide a seamless experience.
    
    Usage:
        orchestrator = InterviewOrchestrator()
        
        # Start session
        await orchestrator.start_session(resume_text, job_description)
        
        # Get first question
        question = await orchestrator.get_next_question()
        
        # Process answer
        feedback = await orchestrator.process_answer(audio_bytes)
        
        # End session
        report = await orchestrator.end_session()
    """
    
    def __init__(
        self,
        gemini: GeminiInterviewer | None = None,
        stt: WhisperSTT | None = None,
        tts: TTSEngine | None = None,
        coach: AudioCoach | None = None,
    ):
        """
        Initialize the orchestrator with all components.
        
        Args:
            gemini: LLM adapter (created if not provided)
            stt: Speech-to-text adapter
            tts: Text-to-speech adapter
            coach: Audio coaching analyzer
        """
        self._settings = get_settings()
        
        # Initialize components
        self._gemini = gemini or GeminiInterviewer()
        self._stt = stt or WhisperSTT()
        self._tts = tts or TTSEngine()
        self._coach = coach or AudioCoach()
        
        # Session state
        self._session: InterviewSession | None = None
        self._question_context: QuestionContext | None = None
        
        # Callbacks for UI updates
        self._on_state_change: Callable[[InterviewState], None] | None = None
        self._on_question: Callable[[str], None] | None = None
        self._on_feedback: Callable[[CoachingFeedback], None] | None = None
    
    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------
    
    @property
    def session(self) -> Optional[InterviewSession]:
        """Get current session."""
        return self._session
    
    @property
    def state(self) -> InterviewState:
        """Get current interview state."""
        if self._session:
            return self._session.state
        return InterviewState.IDLE
    
    @property
    def is_active(self) -> bool:
        """Check if an interview is in progress."""
        return self._session is not None and self._session.state not in [
            InterviewState.IDLE,
            InterviewState.COMPLETE,
            InterviewState.ERROR,
        ]
    
    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------
    
    def set_on_state_change(self, callback: Callable[[InterviewState], None]) -> None:
        """Set callback for state changes."""
        self._on_state_change = callback
    
    def set_on_question(self, callback: Callable[[str], None]) -> None:
        """Set callback for new questions."""
        self._on_question = callback
    
    def set_on_feedback(self, callback: Callable[[CoachingFeedback], None]) -> None:
        """Set callback for coaching feedback."""
        self._on_feedback = callback
    
    def _update_state(self, new_state: InterviewState) -> None:
        """Update session state and notify callback."""
        if self._session:
            self._session.state = new_state
            logger.info(f"State: {new_state.value}")
            if self._on_state_change:
                self._on_state_change(new_state)
    
    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------
    
    async def start_session(
        self,
        resume_text: str,
        job_description: str,
    ) -> str:
        """
        Start a new interview session.
        
        Args:
            resume_text: Extracted resume text
            job_description: Target job description
            
        Returns:
            Session ID
        """
        # Create new session
        session_id = str(uuid.uuid4())[:8]
        
        self._session = InterviewSession(
            session_id=session_id,
            state=InterviewState.SETUP,
            resume_text=resume_text,
            job_description=job_description,
            started_at=datetime.now(),
        )
        
        # Initialize question context
        self._question_context = QuestionContext(
            resume_text=resume_text,
            job_description=job_description,
        )
        
        # Reset coach for new session
        self._coach.reset()
        
        logger.info(f"🎙️ Interview session started: {session_id}")
        self._update_state(InterviewState.INTRO)
        
        return session_id
    
    async def get_next_question(self) -> str:
        """
        Generate and speak the next interview question.
        
        Returns:
            The question text
        """
        if not self._session or not self._question_context:
            raise SessionError("No active session")
        
        self._update_state(InterviewState.QUESTIONING)
        
        try:
            # Generate question based on context
            if not self._question_context.previous_questions:
                # First question - use opening prompt
                question = await self._gemini.generate_opening_question(
                    self._question_context
                )
            else:
                # Subsequent questions
                question = await self._gemini.generate_question(
                    self._question_context
                )
            
            self._session.current_question = question
            self._session.total_questions_asked += 1
            
            logger.info(f"📝 Question {self._session.total_questions_asked}: {question[:50]}...")
            
            # Notify callback
            if self._on_question:
                self._on_question(question)
            
            # Update state to listening
            self._update_state(InterviewState.LISTENING)
            
            return question
            
        except Exception as e:
            logger.error(f"Error generating question: {e}")
            self._update_state(InterviewState.ERROR)
            raise
    
    async def process_answer(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
    ) -> tuple[str, CoachingFeedback, AnswerEvaluation]:
        """
        Process a candidate's spoken answer.
        
        This is the main processing pipeline:
        1. Transcribe audio (STT)
        2. Analyze delivery (Coach)
        3. Evaluate content (Gemini)
        
        Args:
            audio_bytes: Raw audio bytes (WAV format)
            sample_rate: Audio sample rate
            
        Returns:
            Tuple of (transcript, coaching_feedback, evaluation)
        """
        if not self._session:
            raise SessionError("No active session")
        
        self._update_state(InterviewState.EVALUATING)
        
        try:
            # 1. Transcribe audio (offload to thread pool to avoid blocking event loop)
            transcript = await asyncio.to_thread(
                self._stt.transcribe_bytes, audio_bytes, sample_rate
            )
            
            # 2. Calculate duration
            audio_np = audio_bytes_to_numpy(audio_bytes, sample_rate)
            duration = len(audio_np) / sample_rate if audio_np.size > 0 else 0
            
            # 3. Coaching analysis (LOCAL - zero latency, still runs on thread pool for consistency)
            coaching = await asyncio.to_thread(
                self._coach.get_coaching_feedback,
                transcript,
                duration,
                audio_np,
            )
            
            # Notify coaching callback immediately
            if self._on_feedback:
                self._on_feedback(coaching)
            
            # 4. Content evaluation (CLOUD - has latency)
            evaluation = await self._gemini.evaluate_answer(
                question=self._session.current_question,
                answer=transcript,
            )
            
            # 5. Record exchange
            exchange = InterviewExchange(
                question=self._session.current_question,
                answer=transcript,
                answer_duration_seconds=duration,
                evaluation=evaluation,
                coaching_feedback=coaching,
            )
            self._session.add_exchange(exchange)
            
            # 6. Update question context
            if self._question_context:
                self._question_context.add_exchange(
                    self._session.current_question,
                    transcript,
                )
            
            logger.info(f"✅ Processed answer: {len(transcript)} chars, score={evaluation.average_score:.1f}")
            
            return transcript, coaching, evaluation
            
        except Exception as e:
            logger.error(f"Error processing answer: {e}")
            self._update_state(InterviewState.ERROR)
            raise
    
    async def end_session(self) -> dict:
        """
        End the interview session and generate final report.
        
        Returns:
            Session summary dictionary
        """
        if not self._session:
            raise SessionError("No active session")
        
        self._session.ended_at = datetime.now()
        self._update_state(InterviewState.COMPLETE)
        
        summary = self._session.to_summary_dict()
        
        logger.info(f"🏁 Interview complete: {summary}")
        
        return summary
    
    # -------------------------------------------------------------------------
    # TTS Methods
    # -------------------------------------------------------------------------
    
    async def speak_question(self, question: str) -> Optional[bytes]:
        """
        Convert question to speech asynchronously.
        
        Args:
            question: Question text
            
        Returns:
            Audio bytes for playback
        """
        return await asyncio.to_thread(
            self._tts.synthesize_to_bytes, question
        )
    
    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    
    def get_session_stats(self) -> dict:
        """Get current session statistics."""
        if not self._session:
            return {}
        
        return {
            "questions_asked": self._session.total_questions_asked,
            "duration_minutes": round(self._session.duration_minutes, 1),
            "average_score": round(self._session.average_score, 1),
            "average_wpm": round(self._coach.get_average_wpm(), 1),
            "total_fillers": self._session.total_filler_words,
        }
    
    def reset(self) -> None:
        """Reset the orchestrator for a new session."""
        self._session = None
        self._question_context = None
        self._coach.reset()


# -----------------------------------------------------------------------------
# Factory Function
# -----------------------------------------------------------------------------

def create_orchestrator() -> InterviewOrchestrator:
    """Create a fully initialized orchestrator."""
    return InterviewOrchestrator(
        gemini=GeminiInterviewer(),
        stt=WhisperSTT(),
        tts=TTSEngine(),
        coach=AudioCoach(),
    )
