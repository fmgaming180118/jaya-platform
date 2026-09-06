"""
SQLAlchemy models for thesis session persistence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ThesisSession(Base):
    """
    Thesis session model for persistent storage.
    """
    __tablename__ = "thesis_sessions"

    id = Column(String, primary_key=True, index=True)  # session_id (UUID)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    workspace_id = Column(String, default="default", index=True)
    char_count = Column(Integer, default=0)
    status = Column(String, default="uploaded")  # uploaded, analyzing, done, error
    progress = Column(Integer, default=0)
    steps = Column(JSON, default=list)  # list of step dicts
    meta = Column(JSON, default=dict)
    novelty = Column(JSON, default=dict)
    gap_report = Column(Text, default="")
    critique = Column(Text, default="")
    defense_questions = Column(Text, default="")
    analysis = Column(JSON, default=dict)
    error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            "session_id": self.id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "workspace_id": self.workspace_id,
            "char_count": self.char_count,
            "status": self.status,
            "progress": self.progress,
            "steps": self.steps,
            "meta": self.meta,
            "novelty": self.novelty,
            "gap_report": self.gap_report,
            "critique": self.critique,
            "defense_questions": self.defense_questions,
            "analysis": self.analysis,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThesisSession":
        """Create model instance from dictionary."""
        return cls(
            id=data.get("session_id"),
            file_name=data.get("file_name", ""),
            file_path=data.get("file_path", ""),
            workspace_id=data.get("workspace_id", "default"),
            char_count=data.get("char_count", 0),
            status=data.get("status", "uploaded"),
            progress=data.get("progress", 0),
            steps=data.get("steps", []),
            meta=data.get("meta", {}),
            novelty=data.get("novelty", {}),
            gap_report=data.get("gap_report", ""),
            critique=data.get("critique", ""),
            defense_questions=data.get("defense_questions", ""),
            analysis=data.get("analysis", {}),
            error=data.get("error", ""),
        )