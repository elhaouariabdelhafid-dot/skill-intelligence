"""Modèles d'authentification — utilisateurs avec mots de passe hashés + rôles.

SÉCURITÉ :
- Les mots de passe ne sont JAMAIS stockés en clair : on stocke un hash bcrypt.
- bcrypt intègre un "sel" aléatoire par mot de passe → deux utilisateurs avec le
  même mot de passe ont des hash différents, protège contre les rainbow tables.
- Le rôle détermine les permissions (RBAC — Role-Based Access Control).

MULTI-TENANT : chaque utilisateur appartient à une organisation (org_id). Les
données sont isolées par organisation.
"""
from __future__ import annotations

import sys
from datetime import datetime
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from sqlalchemy import (DateTime, ForeignKey, Integer, String, create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, sessionmaker)


class Role(str, Enum):
    """Les 5 rôles du système, du plus au moins privilégié."""
    ADMIN = "admin"            # gestion complète, config système
    RH = "rh"                  # cartographie compétences, tous profils
    MANAGER = "manager"        # son équipe uniquement
    FORMATEUR = "formateur"    # gestion questions, lancer évaluations
    COLLABORATEUR = "collaborateur"  # son propre profil uniquement


class AuthBase(DeclarativeBase):
    pass


class Organization(AuthBase):
    """Une organisation (tenant). Isole les données."""
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthUser(AuthBase):
    """Utilisateur authentifiable. Le mot de passe est stocké hashé."""
    __tablename__ = "auth_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))  # bcrypt, jamais en clair
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), default=Role.COLLABORATEUR.value)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    # lien optionnel vers l'utilisateur métier (table users existante) pour le profil
    profile_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manager_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # pour les équipes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_engine = None
_Session = None


def get_auth_session():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=False)
        AuthBase.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine)
    return _Session()
