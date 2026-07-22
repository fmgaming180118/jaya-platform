"""
Thesis session manager using SQLAlchemy for persistence.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from academic.models import Base, ThesisSession
from config import config

# Database setup
DATABASE_URL = os.getenv(
    "THESIS_DATABASE_URL",
    f"sqlite:///{os.path.join(config.DATA_DIR, 'thesis_sessions.db')}"
)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


class ThesisSessionManager:
    """
    Manager for thesis session operations with persistence.
    """

    def __init__(self):
        self.db: Session = SessionLocal()

    def create_session(self, session_id: str, file_name: str, file_path: str,
                       workspace_id: str = "default") -> ThesisSession:
        """Create a new thesis session."""
        db_session = ThesisSession(
            id=session_id,
            file_name=file_name,
            file_path=file_path,
            workspace_id=workspace_id,
            status="uploaded",
            progress=0,
            steps=[],
            meta={},
            novelty={},
            gap_report="",
            critique="",
            defense_questions="",
            analysis={},
            error=""
        )
        self.db.add(db_session)
        self.db.commit()
        self.db.refresh(db_session)
        return db_session

    def get_session(self, session_id: str) -> Optional[ThesisSession]:
        """Retrieve a session by ID."""
        return self.db.query(ThesisSession).filter(ThesisSession.id == session_id).first()

    def update_session(self, session_id: str, **kwargs) -> Optional[ThesisSession]:
        """Update a session with given fields."""
        db_session = self.get_session(session_id)
        if db_session:
            for key, value in kwargs.items():
                if hasattr(db_session, key):
                    setattr(db_session, key, value)
            db_session.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(db_session)
        return db_session

    def list_sessions(self, workspace_id: Optional[str] = None) -> List[ThesisSession]:
        """List sessions, optionally filtered by workspace."""
        query = self.db.query(ThesisSession)
        if workspace_id:
            query = query.filter(ThesisSession.workspace_id == workspace_id)
        return query.order_by(ThesisSession.created_at.desc()).all()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID."""
        db_session = self.get_session(session_id)
        if db_session:
            self.db.delete(db_session)
            self.db.commit()
            return True
        return False

    def close(self):
        """Close the database session."""
        self.db.close()


# Global instance
thesis_session_manager = ThesisSessionManager()