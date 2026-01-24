"""
InterView AI - Gemini LLM Adapter.

Provides interview-specific functionality using Google Gemini API.
Handles question generation, answer evaluation, and follow-up logic.
"""

from __future__ import annotations

import json
import logging
import re

import google.genai as genai

from src.core.config import get_settings
from src.core.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    MissingAPIKeyError,
)
from src.core.prompts import (
    INTERVIEWER_PERSONA,
    OPENING_QUESTION,
    FOLLOW_UP_PROMPT,
    FEEDBACK_PERSONA,
    INTERVIEW_SUMMARY_PROMPT,
)
from src.core.domain.models import (
    AnswerEvaluation,
    QuestionContext,
)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class GeminiInterviewer:
    """
    Gemini-powered interview AI.
    
    Handles all LLM interactions for the interview system:
    - Generating context-aware questions
    - Evaluating candidate answers
    - Creating follow-up questions
    - Generating final interview reports
    """
    
    def __init__(self, api_key: str | None = None):
        self._settings = get_settings()
        self._api_key = api_key or self._settings.GEMINI_API_KEY
        self._model = None
        self._configured = False
    
    def _configure(self) -> None:
        """Configure the Gemini API client (lazy initialization)."""
        if self._configured:
            return
        
        if not self._api_key:
            raise MissingAPIKeyError("GEMINI_API_KEY")
        
        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel("gemini-2.5-flash-lite")
        self._configured = True
        logger.info("✅ Gemini API configured")
    
    async def generate_opening_question(self, context: QuestionContext) -> str:
        """Generate the first interview question based on resume."""
        self._configure()
        
        prompt = OPENING_QUESTION.format(resume_text=context.resume_text)
        
        return await self._generate(prompt)
    
    async def generate_question(self, context: QuestionContext) -> str:
        """Generate the next interview question."""
        self._configure()
        
        # Format previous questions for context
        prev_q_text = "\n".join(
            f"- {q}" for q in context.previous_questions
        ) if context.previous_questions else "None yet"
        
        prompt = INTERVIEWER_PERSONA.format(
            resume_text=context.resume_text,
            job_description=context.job_description,
            previous_questions=prev_q_text,
        )
        
        return await self._generate(prompt)
    
    async def generate_follow_up(self, answer: str) -> str:
        """Generate a follow-up question based on the candidate's answer."""
        self._configure()
        
        prompt = FOLLOW_UP_PROMPT.format(answer=answer)
        
        return await self._generate(prompt)
    
    async def evaluate_answer(
        self, 
        question: str, 
        answer: str,
    ) -> AnswerEvaluation:
        """Evaluate the candidate's answer and return structured feedback."""
        self._configure()
        
        prompt = FEEDBACK_PERSONA.format(question=question, answer=answer)
        
        try:
            response = await self._generate(prompt)
            return self._parse_evaluation(response)
        except Exception as e:
            logger.warning(f"Failed to parse evaluation: {e}")
            return AnswerEvaluation(
                technical_accuracy=5,
                clarity=5,
                depth=5,
                completeness=5,
                improvement_tip="Unable to evaluate - please continue.",
                positive_note="Keep going!",
            )
    
    async def generate_summary(
        self,
        transcript: str,
        evaluations: list[AnswerEvaluation],
    ) -> str:
        """Generate the final interview summary."""
        self._configure()
        
        eval_text = "\n".join(
            f"Q{i+1}: Tech={e.technical_accuracy}, Clarity={e.clarity}"
            for i, e in enumerate(evaluations)
        )
        
        prompt = INTERVIEW_SUMMARY_PROMPT.format(
            transcript=transcript,
            evaluations=eval_text,
        )
        
        return await self._generate(prompt)
     
    @retry(
        retry=retry_if_exception_type(LLMRateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _generate(self, prompt: str, temperature: float = 0.7) -> str:
        """Internal method to call Gemini API."""
        try:
            generation_config = genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=1024,
            )
            
            response = self._model.generate_content(
                prompt,
                generation_config=generation_config,
            )
            
            if not response.text:
                raise LLMResponseError("Empty response from Gemini")
            
            return response.text.strip()
            
        except genai.types.BlockedPromptException as e:
            logger.warning(f"Prompt blocked: {e}")
            raise LLMResponseError("Content was blocked by safety filters")
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise LLMRateLimitError("Gemini", retry_after=60)
            if "connection" in error_str or "network" in error_str:
                raise LLMConnectionError("Gemini", str(e))
            logger.error(f"Gemini error: {e}")
            raise LLMResponseError(str(e))
    
    def _parse_evaluation(self, response: str) -> AnswerEvaluation:
        """Parse JSON evaluation response from Gemini."""
        # Try to extract JSON from the response
        json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
        
        if not json_match:
            raise ValueError("No JSON found in response")
        
        data = json.loads(json_match.group())
        
        return AnswerEvaluation(
            technical_accuracy=int(data.get("technical_accuracy", 5)),
            clarity=int(data.get("clarity", 5)),
            depth=int(data.get("depth", 5)),
            completeness=int(data.get("completeness", 5)),
            improvement_tip=data.get("improvement_tip", ""),
            positive_note=data.get("positive_note", ""),
        )
