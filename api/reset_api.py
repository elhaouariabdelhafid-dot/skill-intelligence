"""Reinitialisation de mot de passe — demande utilisateur, traitement admin.

POURQUOI CE CIRCUIT : la procedure habituelle envoie un lien de reinitialisation
par courriel. Sans serveur de messagerie, la demande est routee vers
l'administrateur, qui genere un mot de passe provisoire et le transmet — meme
schema que les demandes d'acces.

SECURITE : la reponse a une demande ne revele jamais si l'adresse existe.
Repondre "compte inconnu" permettrait d'enumerer les comptes valides.
"""
from __future__ import annotations

import secrets
import string
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from auth.auth_api import require_role
from auth.auth_models import AuthUser, get_auth_session
from auth.security import hash_password
from api.settings_models import log_action


class PBase(DeclarativeBase):
    pass


class PasswordReset(PBase):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(20), default="en_attente")
    account_exists: Mapped[bool] = mapped_column(default=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


_engine = None
_Session = None


def get_reset_db():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=False)
        PBase.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine)
    return _Session()


router = APIRouter(prefix="/api/reset", tags=["reset"])


class ResetIn(BaseModel):
    email: EmailStr


def temp_password(n: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n)) + "!7"


def _serialize(r: PasswordReset) -> dict:
    return {
        "id": r.id, "email": r.email, "status": r.status,
        "account_exists": r.account_exists, "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.strftime("%d/%m/%Y %H:%M") if r.reviewed_at else None,
        "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else None,
    }


# ══════════════ public ══════════════
@router.post("/request")
def request_reset(data: ResetIn):
    """Enregistre la demande. La reponse est identique que le compte existe ou non."""
    email = data.email.strip().lower()

    a = get_auth_session()
    exists = a.query(AuthUser).filter(AuthUser.email == email).first() is not None
    a.close()

    db = get_reset_db()
    pending = db.query(PasswordReset).filter(
        PasswordReset.email == email,
        PasswordReset.status == "en_attente").first()
    if pending is None:
        db.add(PasswordReset(email=email, account_exists=exists))
        db.commit()
    db.close()

    # Message volontairement neutre : ne pas divulguer l'existence du compte
    return {"submitted": True,
            "message": "Si un compte existe pour cette adresse, "
                       "l'administrateur traitera votre demande."}


# ══════════════ administrateur ══════════════
@router.get("/requests")
def list_resets(status: str | None = None,
                user: dict = Depends(require_role("admin"))):
    db = get_reset_db()
    q = db.query(PasswordReset)
    if status:
        q = q.filter(PasswordReset.status == status)
    rows = [_serialize(r) for r in q.order_by(PasswordReset.id.desc()).all()]
    db.close()
    return rows


@router.get("/pending-count")
def pending_count(user: dict = Depends(require_role("admin"))):
    db = get_reset_db()
    n = db.query(PasswordReset).filter(PasswordReset.status == "en_attente").count()
    db.close()
    return {"pending": n}


@router.post("/requests/{rid}/approve")
def approve_reset(rid: int, user: dict = Depends(require_role("admin"))):
    """Genere un mot de passe provisoire et l'affiche une seule fois."""
    db = get_reset_db()
    r = db.query(PasswordReset).filter(PasswordReset.id == rid).first()
    if r is None:
        db.close(); raise HTTPException(404, "Demande introuvable")
    if r.status != "en_attente":
        db.close(); raise HTTPException(400, f"Demande deja traitee ({r.status})")

    a = get_auth_session()
    acc = a.query(AuthUser).filter(AuthUser.email == r.email).first()
    if acc is None:
        r.status = "sans_objet"
        r.reviewed_by = user["email"]
        r.reviewed_at = datetime.utcnow()
        db.commit(); out = _serialize(r); db.close(); a.close()
        out["temp_password"] = None
        out["note"] = "Aucun compte pour cette adresse."
        return out

    pwd = temp_password()
    acc.password_hash = hash_password(pwd)
    a.commit(); a.close()

    r.status = "traitee"
    r.reviewed_by = user["email"]
    r.reviewed_at = datetime.utcnow()
    db.commit(); out = _serialize(r); db.close()

    log_action(user["email"], "reinitialisation de mot de passe", r.email)
    out["temp_password"] = pwd
    return out


@router.post("/requests/{rid}/reject")
def reject_reset(rid: int, user: dict = Depends(require_role("admin"))):
    db = get_reset_db()
    r = db.query(PasswordReset).filter(PasswordReset.id == rid).first()
    if r is None:
        db.close(); raise HTTPException(404, "Demande introuvable")
    r.status = "refusee"
    r.reviewed_by = user["email"]
    r.reviewed_at = datetime.utcnow()
    db.commit(); out = _serialize(r); db.close()
    log_action(user["email"], "refus de reinitialisation", r.email)
    return out


@router.post("/direct/{account_id}")
def reset_direct(account_id: int, user: dict = Depends(require_role("admin"))):
    """Reinitialisation immediate depuis l'ecran Comptes, sans demande prealable."""
    a = get_auth_session()
    acc = a.query(AuthUser).filter(AuthUser.id == account_id).first()
    if acc is None:
        a.close(); raise HTTPException(404, "Compte introuvable")
    pwd = temp_password()
    acc.password_hash = hash_password(pwd)
    email = acc.email
    a.commit(); a.close()
    log_action(user["email"], "reinitialisation directe", email)
    return {"email": email, "temp_password": pwd}
