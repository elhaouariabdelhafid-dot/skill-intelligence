"""Phase 5 — Modèles de persistance PostgreSQL (SQLAlchemy).

POURQUOI stocker en base : le profil de compétences se construit à partir de
TOUTES les évaluations d'un collaborateur dans le temps. Sans persistance, on
recalcule tout à chaque fois et on perd l'historique — or le suivi de l'évolution
est justement un objectif de ton projet.

Les tables reprennent le schéma de scripts/init_db.sql, en version ORM.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from sqlalchemy import (DateTime, Float, ForeignKey, Integer, String, Text,
                        create_engine, JSON)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(60), default="collaborator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    question_id: Mapped[str] = mapped_column(String(32))
    skill: Mapped[str] = mapped_column(String(120))
    service: Mapped[str] = mapped_column(String(60))
    bloom_level: Mapped[str] = mapped_column(String(20))
    difficulty: Mapped[str] = mapped_column(String(20))
    answer_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    grader_score: Mapped[float] = mapped_column(Float)
    reasoner_score: Mapped[float] = mapped_column(Float)
    critic_score: Mapped[float] = mapped_column(Float)
    final_score: Mapped[float] = mapped_column(Float)
    feedback: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_engine = None
_Session = None


def get_session():
    """Retourne une session SQLAlchemy, crée les tables au premier appel."""
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=False)
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine)
    return _Session()
