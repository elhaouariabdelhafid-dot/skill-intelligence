"""Demandes d'évaluation — circuit manager → RH → formateur.

POURQUOI ce circuit : dans une organisation réelle, le manager identifie un
besoin sur son équipe mais n'arbitre pas seul ; les RH valident au regard du
plan de formation et des priorités ; le formateur exécute. Ce workflow rend
le système utilisable comme outil central de gestion des compétences.

CYCLE DE VIE :
    en_attente ──(RH valide)──► validée ──(formateur crée la session)──► planifiée
         └──────(RH refuse)───► refusée
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from sqlalchemy import (JSON, DateTime, Integer, String, Text, create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class RBase(DeclarativeBase):
    pass


class EvalRequest(RBase):
    __tablename__ = "eval_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Émetteur (manager)
    requested_by: Mapped[str] = mapped_column(String(200))      # email
    requester_name: Mapped[str] = mapped_column(String(160))

    # Contenu de la demande
    title: Mapped[str] = mapped_column(String(200))
    justification: Mapped[str] = mapped_column(Text)             # pourquoi ce besoin
    services: Mapped[list] = mapped_column(JSON, default=list)
    participants: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(String(20), default="normale")  # basse/normale/haute

    # Traitement RH
    status: Mapped[str] = mapped_column(String(20), default="en_attente")
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Exécution formateur
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_engine = None
_Session = None


def get_requests_db():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=False)
        RBase.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine)
    return _Session()
