"""Modèles des sessions d'évaluation (examens).

CYCLE DE VIE d'une session :
    brouillon → sujet généré → ouverte (les collaborateurs répondent)
              → évaluation en cours → terminée

Trois tables :
  EvalSession      la session elle-même (titre, services, participants, statut)
  SessionQuestion  les questions retenues pour cette session
  SessionAnswer    les réponses des participants (avant et après évaluation)

SessionAnswer.submission_id relie la réponse au système existant : une fois
évaluée, elle produit une Submission + une Evaluation comme import_forms.py.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from sqlalchemy import (JSON, DateTime, ForeignKey, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class SBase(DeclarativeBase):
    pass


class EvalSession(SBase):
    __tablename__ = "eval_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(200))          # email du formateur
    services: Mapped[list] = mapped_column(JSON, default=list)     # services couverts
    participants: Mapped[list] = mapped_column(JSON, default=list) # ids dans la table users
    status: Mapped[str] = mapped_column(String(30), default="brouillon")
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionQuestion(SBase):
    __tablename__ = "session_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("eval_sessions.id"))
    question_id: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)


class SessionAnswer(SBase):
    __tablename__ = "session_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("eval_sessions.id"))
    user_id: Mapped[int] = mapped_column(Integer)          # id dans la table users
    question_id: Mapped[str] = mapped_column(String(64))
    answer_text: Mapped[str] = mapped_column(Text)
    submission_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_engine = None
_Session = None


def get_sessions_db():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=False)
        SBase.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine)
    return _Session()
