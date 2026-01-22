"""
InterView AI - SQLite Session Repository.

SQL-based session persistence for production-grade crash resistance.
Replaces JSON with proper relational schema for scalability and query flexibility.

Usage:
    repo = SQLiteSessionRepository()
    
    # Save after each answer
    repo.save(session)
    
    # Restore on server restart
    session = repo.load(session_id)
    
    # Clean up old sessions
    repo.cleanup_old_sessions(max_age_hours=24)
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from src.core.domain.models import (
    InterviewSession,
    InterviewState,
    InterviewExchange,
    AnswerEvaluation,
    CoachingFeedback,
    CoachingAlertLevel,
)

logger = logging.getLogger(__name__)


class SQLiteSessionRepository:
    """
    SQLite-based session persistence.
    
    Stores session state in a relational database, enabling:
    - Crash recovery with transactional guarantees
    - Query flexibility (e.g., find all sessions from today)
    - Multi-worker support via file-based SQLite
    """
    
    def __init__(self, db_path: str = "data/sessions.db"):
        """
        Initialize repository with SQLite database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema on first run
        self._initialize_schema()
        logger.info(f"SQLite repository initialized at: {self._db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with proper settings."""
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row  # Access columns by name
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for concurrency
        return conn
    
    def _initialize_schema(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    resume_text TEXT,
                    job_description TEXT,
                    current_question TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    total_questions_asked INTEGER DEFAULT 0,
                    total_filler_words INTEGER DEFAULT 0,
                    average_wpm REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Exchanges table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exchanges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question TEXT,
                    answer TEXT,
                    answer_duration_seconds REAL DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Evaluations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange_id INTEGER NOT NULL,
                    technical_accuracy INTEGER,
                    clarity INTEGER,
                    depth INTEGER,
                    completeness INTEGER,
                    improvement_tip TEXT,
                    positive_note TEXT,
                    FOREIGN KEY (exchange_id) REFERENCES exchanges(id)
                )
            """)
            
            # Coaching feedback table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS coaching_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange_id INTEGER NOT NULL,
                    volume_status TEXT,
                    pace_status TEXT,
                    filler_count INTEGER,
                    words_per_minute REAL,
                    primary_alert TEXT,
                    alert_level TEXT,
                    FOREIGN KEY (exchange_id) REFERENCES exchanges(id)
                )
            """)
            
            # Create indices for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_exchanges_session ON exchanges(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at)")
            
            conn.commit()
            logger.info("✅ Database schema initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def save(self, session: InterviewSession) -> None:
        """
        Persist session to SQLite database.
        
        Args:
            session: InterviewSession to persist
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            now = datetime.now().isoformat()
            
            # Check if session exists
            cursor.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session.session_id,))
            exists = cursor.fetchone() is not None
            
            if exists:
                # Update session
                cursor.execute("""
                    UPDATE sessions SET
                        state = ?,
                        current_question = ?,
                        ended_at = ?,
                        total_questions_asked = ?,
                        total_filler_words = ?,
                        average_wpm = ?,
                        updated_at = ?
                    WHERE session_id = ?
                """, (
                    session.state.value,
                    session.current_question,
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.total_questions_asked,
                    session.total_filler_words,
                    session.average_wpm,
                    now,
                    session.session_id,
                ))
            else:
                # Insert new session
                cursor.execute("""
                    INSERT INTO sessions (
                        session_id, state, resume_text, job_description,
                        current_question, started_at, ended_at,
                        total_questions_asked, total_filler_words, average_wpm,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.session_id,
                    session.state.value,
                    session.resume_text,
                    session.job_description,
                    session.current_question,
                    session.started_at.isoformat() if session.started_at else None,
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.total_questions_asked,
                    session.total_filler_words,
                    session.average_wpm,
                    now,
                    now,
                ))
            
            # Save exchanges (delete old ones first to avoid duplicates)
            cursor.execute("DELETE FROM exchanges WHERE session_id = ?", (session.session_id,))
            
            for exchange in session.exchanges:
                cursor.execute("""
                    INSERT INTO exchanges (
                        session_id, question, answer, answer_duration_seconds,
                        timestamp, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    session.session_id,
                    exchange.question,
                    exchange.answer,
                    exchange.answer_duration_seconds,
                    exchange.timestamp.isoformat(),
                    now,
                ))
                
                exchange_id = cursor.lastrowid
                
                # Save evaluation if present
                if exchange.evaluation:
                    cursor.execute("""
                        INSERT INTO evaluations (
                            exchange_id, technical_accuracy, clarity, depth,
                            completeness, improvement_tip, positive_note
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        exchange_id,
                        exchange.evaluation.technical_accuracy,
                        exchange.evaluation.clarity,
                        exchange.evaluation.depth,
                        exchange.evaluation.completeness,
                        exchange.evaluation.improvement_tip,
                        exchange.evaluation.positive_note,
                    ))
                
                # Save coaching feedback if present
                if exchange.coaching_feedback:
                    cursor.execute("""
                        INSERT INTO coaching_feedback (
                            exchange_id, volume_status, pace_status, filler_count,
                            words_per_minute, primary_alert, alert_level
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        exchange_id,
                        exchange.coaching_feedback.volume_status,
                        exchange.coaching_feedback.pace_status,
                        exchange.coaching_feedback.filler_count,
                        exchange.coaching_feedback.words_per_minute,
                        exchange.coaching_feedback.primary_alert,
                        exchange.coaching_feedback.alert_level.value,
                    ))
            
            conn.commit()
            logger.debug(f"Saved session {session.session_id} ({len(session.exchanges)} exchanges)")
            
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def load(self, session_id: str) -> Optional[InterviewSession]:
        """
        Load session from SQLite database.
        
        Args:
            session_id: Session ID to load
            
        Returns:
            InterviewSession if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Load session
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            
            if not row:
                logger.debug(f"Session {session_id} not found")
                return None
            
            session = InterviewSession(
                session_id=row["session_id"],
                state=InterviewState(row["state"]),
                resume_text=row["resume_text"],
                job_description=row["job_description"],
                current_question=row["current_question"],
                started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                total_questions_asked=row["total_questions_asked"],
                total_filler_words=row["total_filler_words"],
                average_wpm=row["average_wpm"],
            )
            
            # Load exchanges
            cursor.execute("""
                SELECT e.id, e.question, e.answer, e.answer_duration_seconds, e.timestamp,
                       ev.technical_accuracy, ev.clarity, ev.depth, ev.completeness,
                       ev.improvement_tip, ev.positive_note,
                       cf.volume_status, cf.pace_status, cf.filler_count,
                       cf.words_per_minute, cf.primary_alert, cf.alert_level
                FROM exchanges e
                LEFT JOIN evaluations ev ON e.id = ev.exchange_id
                LEFT JOIN coaching_feedback cf ON e.id = cf.exchange_id
                WHERE e.session_id = ?
                ORDER BY e.id
            """, (session_id,))
            
            for ex_row in cursor.fetchall():
                # Reconstruct evaluation
                evaluation = None
                if ex_row["technical_accuracy"] is not None:
                    evaluation = AnswerEvaluation(
                        technical_accuracy=ex_row["technical_accuracy"],
                        clarity=ex_row["clarity"],
                        depth=ex_row["depth"],
                        completeness=ex_row["completeness"],
                        improvement_tip=ex_row["improvement_tip"],
                        positive_note=ex_row["positive_note"],
                    )
                
                # Reconstruct coaching feedback
                coaching = None
                if ex_row["volume_status"] is not None:
                    coaching = CoachingFeedback(
                        volume_status=ex_row["volume_status"],
                        pace_status=ex_row["pace_status"],
                        filler_count=ex_row["filler_count"],
                        words_per_minute=ex_row["words_per_minute"],
                        primary_alert=ex_row["primary_alert"],
                        alert_level=CoachingAlertLevel(ex_row["alert_level"]),
                    )
                
                exchange = InterviewExchange(
                    question=ex_row["question"],
                    answer=ex_row["answer"],
                    answer_duration_seconds=ex_row["answer_duration_seconds"],
                    evaluation=evaluation,
                    coaching_feedback=coaching,
                    timestamp=datetime.fromisoformat(ex_row["timestamp"]),
                )
                session.exchanges.append(exchange)
            
            logger.info(f"Loaded session {session_id} from DB ({len(session.exchanges)} exchanges)")
            return session
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
        finally:
            conn.close()
    
    def delete(self, session_id: str) -> bool:
        """
        Delete session and its exchanges from database.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
            if not cursor.fetchone():
                return False
            
            # Delete exchanges (cascade deletes evaluations and coaching via foreign key)
            cursor.execute("DELETE FROM exchanges WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            
            conn.commit()
            logger.info(f"Deleted session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def list_sessions(self) -> list[str]:
        """
        List all stored session IDs.
        
        Returns:
            List of session IDs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT session_id FROM sessions ORDER BY created_at DESC")
            return [row["session_id"] for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """
        Delete sessions older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours before cleanup
            
        Returns:
            Number of sessions cleaned up
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
            
            # Get sessions to delete
            cursor.execute(
                "SELECT session_id FROM sessions WHERE created_at < ?",
                (cutoff,)
            )
            session_ids = [row["session_id"] for row in cursor.fetchall()]
            
            # Delete sessions
            for sid in session_ids:
                cursor.execute("DELETE FROM exchanges WHERE session_id = ?", (sid,))
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
            
            conn.commit()
            
            if session_ids:
                logger.info(f"Cleaned up {len(session_ids)} old sessions")
            
            return len(session_ids)
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()
    
    def get_session_stats(self) -> dict:
        """
        Get statistics about stored sessions.
        
        Returns:
            Dictionary with total sessions, total exchanges, etc.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as count FROM sessions")
            total_sessions = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM exchanges")
            total_exchanges = cursor.fetchone()["count"]
            
            return {
                "total_sessions": total_sessions,
                "total_exchanges": total_exchanges,
                "database_size_mb": self._db_path.stat().st_size / (1024 * 1024),
            }
        finally:
            conn.close()
