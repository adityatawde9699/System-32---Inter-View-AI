"""
InterView AI - PDF Parser.

Extracts text from resume PDFs using pypdf.
Handles edge cases like encrypted PDFs and empty pages.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional, Union

from src.core.exceptions import PDFParseError, EmptyDocumentError


logger = logging.getLogger(__name__)


# Check for pypdf availability
try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False
    logger.warning("⚠️ pypdf not installed. PDF parsing will use mock data.")


def extract_resume_text(pdf_path: Union[str, Path]) -> str:
    """
    Extract text content from a resume PDF.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text content
        
    Raises:
        PDFParseError: If PDF cannot be read
        EmptyDocumentError: If PDF has no extractable text
    """
    pdf_path = Path(pdf_path)
    
    # Validate file exists
    if not pdf_path.exists():
        raise PDFParseError(str(pdf_path), "File not found")
    
    if not pdf_path.suffix.lower() == ".pdf":
        raise PDFParseError(str(pdf_path), "File is not a PDF")
    
    # Fallback if pypdf unavailable
    if not PYPDF_AVAILABLE:
        logger.warning("📄 [Fallback] Using mock resume text")
        return _mock_resume_text()
    
    try:
        reader = PdfReader(str(pdf_path))
        
        # Check for encryption
        if reader.is_encrypted:
            try:
                reader.decrypt("")  # Try empty password
            except Exception:
                raise PDFParseError(str(pdf_path), "PDF is encrypted")
        
        # Extract text from all pages
        text_parts = []
        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"Could not extract page {page_num + 1}: {e}")
        
        if not text_parts:
            raise EmptyDocumentError("PDF has no extractable text content")
        
        # Combine and clean text
        full_text = "\n\n".join(text_parts)
        cleaned_text = _clean_text(full_text)
        
        logger.info(f"✅ Extracted {len(cleaned_text)} chars from {pdf_path.name}")
        return cleaned_text
        
    except (PDFParseError, EmptyDocumentError):
        raise
    except Exception as e:
        logger.error(f"PDF parsing error: {e}")
        raise PDFParseError(str(pdf_path), str(e))


def extract_from_bytes(pdf_bytes: bytes, filename: str = "resume.pdf") -> str:
    """
    Extract text from PDF bytes (for uploaded files).
    
    Args:
        pdf_bytes: Raw PDF file bytes
        filename: Original filename for error messages
        
    Returns:
        Extracted text content
    """
    import tempfile
    
    # Write to temp file for processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(pdf_bytes)
        temp_path = f.name
    
    try:
        return extract_resume_text(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def parse_job_description(jd_text: str) -> dict:
    """
    Parse and structure a job description.
    
    Args:
        jd_text: Raw job description text
        
    Returns:
        Structured job description with sections
    """
    cleaned = _clean_text(jd_text)
    
    # Extract key sections using simple heuristics
    sections = {
        "title": "",
        "requirements": [],
        "responsibilities": [],
        "full_text": cleaned,
    }
    
    # Try to find job title (usually at the start)
    lines = cleaned.split("\n")
    if lines:
        sections["title"] = lines[0].strip()
    
    # Extract requirements (look for keywords)
    req_keywords = ["requirement", "qualific", "skill", "experience"]
    resp_keywords = ["responsib", "duties", "what you'll do", "role"]
    
    current_section = None
    for line in lines:
        line_lower = line.lower()
        
        if any(kw in line_lower for kw in req_keywords):
            current_section = "requirements"
        elif any(kw in line_lower for kw in resp_keywords):
            current_section = "responsibilities"
        elif current_section and line.strip().startswith(("-", "•", "*", "–")):
            sections[current_section].append(line.strip(" -•*–"))
    
    return sections


def _clean_text(text: str) -> str:
    """Clean and normalize extracted text."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common PDF artifacts
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Normalize line breaks
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def _mock_resume_text() -> str:
    """Return mock resume text for testing without pypdf."""
    return """
John Doe
Software Engineer | john.doe@email.com | github.com/johndoe

EXPERIENCE

Software Engineer Intern - Tech Company (June 2024 - August 2024)
• Developed a Flask REST API with PostgreSQL backend for user management
• Implemented JWT authentication and role-based access control
• Wrote unit tests achieving 85% code coverage

Open Source Contributor - Amadeus AI Project
• Built a voice-controlled AI assistant using Python and Gemini API
• Integrated Whisper for speech-to-text transcription
• Created a ReAct agent pattern for multi-step reasoning

EDUCATION

B.Tech in Computer Science - University Name (2021-2025)
• GPA: 3.8/4.0
• Relevant coursework: Data Structures, Algorithms, Database Systems, ML

SKILLS

Languages: Python, JavaScript, SQL, TypeScript
Frameworks: Flask, FastAPI, React, Next.js
Tools: Git, Docker, PostgreSQL, Redis
    """.strip()
