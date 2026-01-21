"""
InterView AI - Orchestrator Tests.

Comprehensive unit tests for the state machine and integration points.
Tests the interview flow with mocked LLM, STT, and TTS components.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from src.app.orchestrator import InterviewOrchestrator, create_orchestrator
from src.core.domain.models import (
    InterviewState,
    InterviewSession,
    AnswerEvaluation,
    CoachingFeedback,
    CoachingAlertLevel,
)
from src.core.exceptions import (
    InvalidSessionStateError,
    SessionError,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_gemini():
    """Mock GeminiInterviewer."""
    mock = AsyncMock()
    mock.generate_opening_question = AsyncMock(
        return_value="Tell me about yourself and your background."
    )
    mock.generate_question = AsyncMock(
        return_value="What's your experience with Python?"
    )
    mock.evaluate_answer = AsyncMock(
        return_value=AnswerEvaluation(
            technical_accuracy=8,
            clarity=8,
            depth=7,
            completeness=8,
            improvement_tip="Could add more specific examples.",
            positive_note="Great explanation of design patterns.",
        )
    )
    return mock


@pytest.fixture
def mock_stt():
    """Mock WhisperSTT."""
    mock = Mock()
    mock.transcribe_bytes = Mock(
        return_value="I have five years of experience with Python and FastAPI."
    )
    return mock


@pytest.fixture
def mock_tts():
    """Mock TTSEngine."""
    mock = Mock()
    mock.synthesize_to_bytes = Mock(return_value=b"audio_bytes")
    return mock


@pytest.fixture
def mock_coach():
    """Mock AudioCoach."""
    mock = Mock()
    mock.get_coaching_feedback = Mock(
        return_value=CoachingFeedback(
            volume_status="OK",
            pace_status="OK",
            filler_count=2,
            words_per_minute=125,
            primary_alert="",
            alert_level=CoachingAlertLevel.OK,
        )
    )
    mock.reset = Mock()
    mock.get_average_wpm = Mock(return_value=125)
    return mock


@pytest.fixture
def orchestrator(mock_gemini, mock_stt, mock_tts, mock_coach):
    """Create orchestrator with mocked components."""
    return InterviewOrchestrator(
        gemini=mock_gemini,
        stt=mock_stt,
        tts=mock_tts,
        coach=mock_coach,
    )


@pytest.fixture
def sample_resume():
    """Sample resume text."""
    return """
    John Doe
    Senior Software Engineer
    
    Experience:
    - 5 years with Python, FastAPI, PostgreSQL
    - Led team of 3 engineers
    - Built microservices for payment processing
    """


@pytest.fixture
def sample_job_description():
    """Sample job description."""
    return """
    Senior Backend Engineer
    Requirements:
    - 5+ years Python experience
    - Experience with async frameworks
    - System design knowledge
    """


# ============================================================================
# Session Lifecycle Tests
# ============================================================================

class TestSessionLifecycle:
    """Test complete interview session flow."""
    
    @pytest.mark.asyncio
    async def test_start_session(self, orchestrator, sample_resume, sample_job_description):
        """Test session creation and initialization."""
        session_id = await orchestrator.start_session(sample_resume, sample_job_description)
        
        assert session_id is not None
        assert isinstance(session_id, str)
        assert orchestrator.session is not None
        assert orchestrator.session.resume_text == sample_resume
        assert orchestrator.session.job_description == sample_job_description
        assert orchestrator.session.state == InterviewState.INTRO
        assert orchestrator.session.total_questions_asked == 0
    
    @pytest.mark.asyncio
    async def test_session_state_progression(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test state machine transitions."""
        # Start session
        await orchestrator.start_session(sample_resume, sample_job_description)
        assert orchestrator.state == InterviewState.INTRO  # INTRO after start, not SETUP
        
        # Get first question
        question = await orchestrator.get_next_question()
        assert question is not None
        assert orchestrator.state == InterviewState.LISTENING
        
        # Process answer
        transcript, coaching, evaluation = await orchestrator.process_answer(
            audio_bytes=b"audio_data",
            sample_rate=16000,
        )
        assert orchestrator.state == InterviewState.EVALUATING
        
        # End session
        summary = await orchestrator.end_session()
        assert orchestrator.state == InterviewState.COMPLETE
        assert summary["total_questions"] == 1
    
    @pytest.mark.asyncio
    async def test_cannot_process_answer_without_session(self, orchestrator):
        """Test error when processing answer without active session."""
        with pytest.raises(SessionError):
            await orchestrator.process_answer(b"audio", 16000)
    
    @pytest.mark.asyncio
    async def test_cannot_get_question_without_session(self, orchestrator):
        """Test error when getting question without active session."""
        with pytest.raises(SessionError):
            await orchestrator.get_next_question()


# ============================================================================
# Question Generation Tests
# ============================================================================

class TestQuestionGeneration:
    """Test question generation pipeline."""
    
    @pytest.mark.asyncio
    async def test_opening_question_for_first_question(
        self, orchestrator, mock_gemini, sample_resume, sample_job_description
    ):
        """Test that opening question is used for first question."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        
        await orchestrator.get_next_question()
        
        # Should call opening question
        mock_gemini.generate_opening_question.assert_called_once()
        mock_gemini.generate_question.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_subsequent_questions(
        self, orchestrator, mock_gemini, sample_resume, sample_job_description
    ):
        """Test that subsequent questions use generate_question."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        
        # First question
        await orchestrator.get_next_question()
        
        # Answer it
        await orchestrator.process_answer(b"audio1", 16000)
        
        # Second question
        await orchestrator.get_next_question()
        
        # Should have called generate_question
        mock_gemini.generate_question.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_question_context_accumulates(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test that question context accumulates with each exchange."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        
        # Answer first question
        await orchestrator.get_next_question()
        await orchestrator.process_answer(b"audio1", 16000)
        
        # Answer second question
        await orchestrator.get_next_question()
        await orchestrator.process_answer(b"audio2", 16000)
        
        # Verify exchanges recorded
        assert len(orchestrator.session.exchanges) == 2


# ============================================================================
# Answer Processing Tests
# ============================================================================

class TestAnswerProcessing:
    """Test answer processing pipeline."""
    
    @pytest.mark.asyncio
    async def test_answer_transcription(
        self, orchestrator, mock_stt, sample_resume, sample_job_description
    ):
        """Test that audio is transcribed."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        await orchestrator.get_next_question()
        
        transcript, _, _ = await orchestrator.process_answer(b"audio_data", 16000)
        
        # STT should have been called
        mock_stt.transcribe_bytes.assert_called_once()
        assert transcript == "I have five years of experience with Python and FastAPI."
    
    @pytest.mark.asyncio
    async def test_coaching_feedback_generated(
        self, orchestrator, mock_coach, sample_resume, sample_job_description
    ):
        """Test that coaching feedback is generated."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        await orchestrator.get_next_question()
        
        _, coaching, _ = await orchestrator.process_answer(b"audio_data", 16000)
        
        # Coach should have been called
        mock_coach.get_coaching_feedback.assert_called_once()
        assert coaching.volume_status == "OK"
        assert coaching.filler_count == 2
    
    @pytest.mark.asyncio
    async def test_answer_evaluation(
        self, orchestrator, mock_gemini, sample_resume, sample_job_description
    ):
        """Test that answer is evaluated by LLM."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        await orchestrator.get_next_question()
        
        _, _, evaluation = await orchestrator.process_answer(b"audio_data", 16000)
        
        # Gemini should have evaluated
        mock_gemini.evaluate_answer.assert_called_once()
        assert evaluation.technical_accuracy == 8
        assert evaluation.clarity == 8
    
    @pytest.mark.asyncio
    async def test_exchange_recorded(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test that exchange is recorded in session."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        await orchestrator.get_next_question()
        
        await orchestrator.process_answer(b"audio_data", 16000)
        
        # Exchange should be in session
        assert len(orchestrator.session.exchanges) == 1
        exchange = orchestrator.session.exchanges[0]
        assert exchange.answer is not None
        assert exchange.evaluation is not None
        assert exchange.coaching_feedback is not None


# ============================================================================
# TTS Tests
# ============================================================================

class TestTextToSpeech:
    """Test text-to-speech functionality."""
    
    @pytest.mark.asyncio
    async def test_speak_question(self, orchestrator, mock_tts):
        """Test that question can be synthesized to speech."""
        audio_bytes = await orchestrator.speak_question("What is your background?")
        
        mock_tts.synthesize_to_bytes.assert_called_once()
        assert audio_bytes == b"audio_bytes"


# ============================================================================
# Session Statistics Tests
# ============================================================================

class TestSessionStatistics:
    """Test session statistics tracking."""
    
    @pytest.mark.asyncio
    async def test_stats_accumulate(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test that statistics accumulate correctly."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        
        # Answer 2 questions
        for _ in range(2):
            await orchestrator.get_next_question()
            await orchestrator.process_answer(b"audio_data", 16000)
        
        stats = orchestrator.get_session_stats()
        
        assert stats["questions_asked"] == 2
        assert stats["average_score"] > 0
        assert stats["average_wpm"] > 0
        assert stats["total_fillers"] >= 0
    
    @pytest.mark.asyncio
    async def test_stats_empty_without_session(self, orchestrator):
        """Test that stats are empty without session."""
        stats = orchestrator.get_session_stats()
        assert stats == {}


# ============================================================================
# Callback Tests
# ============================================================================

class TestCallbacks:
    """Test callback mechanisms."""
    
    @pytest.mark.asyncio
    async def test_state_change_callback(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test state change callback is called."""
        callback = Mock()
        orchestrator.set_on_state_change(callback)
        
        await orchestrator.start_session(sample_resume, sample_job_description)
        
        # Callback should have been called for state transitions (INTRO after start)
        assert callback.called
        assert any(
            call[0][0] == InterviewState.INTRO
            for call in callback.call_args_list
        )
    
    @pytest.mark.asyncio
    async def test_question_callback(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test question callback is called."""
        callback = Mock()
        orchestrator.set_on_question(callback)
        
        await orchestrator.start_session(sample_resume, sample_job_description)
        await orchestrator.get_next_question()
        
        # Callback should have been called with question
        callback.assert_called_once()
        question = callback.call_args[0][0]
        assert isinstance(question, str)
        assert len(question) > 0
    
    @pytest.mark.asyncio
    async def test_feedback_callback(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test coaching feedback callback is called."""
        callback = Mock()
        orchestrator.set_on_feedback(callback)
        
        await orchestrator.start_session(sample_resume, sample_job_description)
        await orchestrator.get_next_question()
        await orchestrator.process_answer(b"audio_data", 16000)
        
        # Callback should have been called with coaching
        callback.assert_called_once()
        coaching = callback.call_args[0][0]
        assert isinstance(coaching, CoachingFeedback)


# ============================================================================
# Reset Tests
# ============================================================================

class TestReset:
    """Test reset functionality."""
    
    @pytest.mark.asyncio
    async def test_reset_clears_session(
        self, orchestrator, sample_resume, sample_job_description
    ):
        """Test that reset clears the session."""
        await orchestrator.start_session(sample_resume, sample_job_description)
        assert orchestrator.session is not None
        
        orchestrator.reset()
        
        assert orchestrator.session is None
        assert orchestrator.state == InterviewState.IDLE
