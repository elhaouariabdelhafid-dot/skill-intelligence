"""Demandes d'acces a la plateforme (inscription controlee).

POURQUOI PAS D'INSCRIPTION LIBRE : la plateforme attribue des roles qui donnent
acces a des donnees sensibles (profils, evaluations). Un visiteur ne choisit pas
son role : il en fait la demande, l'administrateur decide.

CYCLE DE VIE :
    en_attente ──(approuvee)──► compte cree, mot de passe provisoire transmis
         └──────(refusee)────► archivee avec motif
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class ABase(DeclarativeBase):
    pass


class AccessRequest(ABase):
    __tablename__ = "access_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200), index=True)
    requested_role: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="en_attente")
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_engine = None
_Session = None


def get_access_db():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=False)
        ABase.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine)
    return _Session()
