"""Endpoints des demandes d'acces.

PUBLIC     : POST /api/access/request  — un visiteur soumet sa demande
ADMIN      : consulte la file, approuve (cree le compte) ou refuse

L'approbation genere un mot de passe provisoire. Dans un deploiement reel il
serait envoye par courriel ; ici il est retourne a l'administrateur qui le
transmet. Le mot de passe est hashe avant enregistrement, comme tout autre.
"""
from __future__ import annotations

import secrets
import string
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from auth.auth_api import require_role
from auth.auth_models import AuthUser, Organization, Role, get_auth_session
from auth.security import hash_password
from api.access_models import AccessRequest, get_access_db
from api.settings_models import log_action

router = APIRouter(prefix="/api/access", tags=["access"])


class AccessIn(BaseModel):
    full_name: str
    email: EmailStr
    requested_role: str = "collaborateur"
    reason: str = ""


class DecisionIn(BaseModel):
    decision: str          # "approuvee" ou "refusee"
    role: str | None = None    # role finalement accorde (peut differer du demande)
    comment: str = ""


def _serialize(r: AccessRequest) -> dict:
    return {
        "id": r.id, "full_name": r.full_name, "email": r.email,
        "requested_role": r.requested_role, "reason": r.reason,
        "status": r.status, "reviewed_by": r.reviewed_by,
        "review_comment": r.review_comment,
        "reviewed_at": r.reviewed_at.strftime("%d/%m/%Y %H:%M") if r.reviewed_at else None,
        "created_account_id": r.created_account_id,
        "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else None,
    }


def _temp_password(n: int = 12) -> str:
    """Mot de passe provisoire lisible mais imprevisible."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n)) + "!7"


# ══════════════ public ══════════════
@router.post("/request")
def submit_request(data: AccessIn):
    """Ouvert sans authentification : c'est le formulaire de la page d'accueil."""
    if data.requested_role not in [r.value for r in Role]:
        raise HTTPException(400, "Role demande invalide")

    email = data.email.strip().lower()

    asess = get_auth_session()
    exists = asess.query(AuthUser).filter(AuthUser.email == email).first()
    asess.close()
    if exists:
        raise HTTPException(400, "Un compte existe deja pour cette adresse")

    db = get_access_db()
    pending = db.query(AccessRequest).filter(
        AccessRequest.email == email, AccessRequest.status == "en_attente").first()
    if pending:
        db.close()
        raise HTTPException(400, "Une demande est deja en cours pour cette adresse")

    r = AccessRequest(full_name=data.full_name.strip(), email=email,
                      requested_role=data.requested_role,
                      reason=data.reason.strip(), status="en_attente")
    db.add(r); db.commit()
    out = {"submitted": True, "id": r.id}
    db.close()
    return out


# ══════════════ administrateur ══════════════
@router.get("/requests")
def list_requests(status: str | None = None,
                  user: dict = Depends(require_role("admin"))):
    db = get_access_db()
    q = db.query(AccessRequest)
    if status:
        q = q.filter(AccessRequest.status == status)
    rows = q.order_by(AccessRequest.id.desc()).all()
    out = [_serialize(r) for r in rows]
    db.close()
    return out


@router.get("/pending-count")
def pending_count(user: dict = Depends(require_role("admin"))):
    """Alimente le badge de notification du menu."""
    db = get_access_db()
    n = db.query(AccessRequest).filter(AccessRequest.status == "en_attente").count()
    db.close()
    return {"pending": n}


@router.post("/requests/{rid}/decide")
def decide(rid: int, data: DecisionIn, user: dict = Depends(require_role("admin"))):
    """Approuve (cree le compte) ou refuse une demande."""
    if data.decision not in ("approuvee", "refusee"):
        raise HTTPException(400, "Decision invalide")

    db = get_access_db()
    r = db.query(AccessRequest).filter(AccessRequest.id == rid).first()
    if r is None:
        db.close(); raise HTTPException(404, "Demande introuvable")
    if r.status != "en_attente":
        db.close(); raise HTTPException(400, f"Demande deja traitee ({r.status})")

    temp_pwd = None
    if data.decision == "approuvee":
        role = data.role or r.requested_role
        if role not in [x.value for x in Role]:
            db.close(); raise HTTPException(400, "Role invalide")

        asess = get_auth_session()
        if asess.query(AuthUser).filter(AuthUser.email == r.email).first():
            asess.close(); db.close()
            raise HTTPException(400, "Un compte existe deja pour cette adresse")

        org = asess.query(Organization).filter(Organization.name == "CMH").first()
        if not org:
            org = Organization(name="CMH")
            asess.add(org); asess.commit()

        asess.close()
        # Meme chemin que l'onboarding RH : compte ET profil metier
        from api.onboarding import create_member
        created = create_member(r.full_name, r.email, role, user["email"])
        temp_pwd = created["temp_password"]
        r.created_account_id = created["account_id"]
        log_action(user["email"], "creation de compte",
                   f"{r.email} · role {role} · via demande #{r.id}")
    else:
        log_action(user["email"], "refus de demande d'acces",
                   f"{r.email} · motif : {data.comment[:100]}")

    r.status = data.decision
    r.reviewed_by = user["email"]
    r.review_comment = data.comment
    r.reviewed_at = datetime.utcnow()
    db.commit()
    out = _serialize(r)
    db.close()
    out["temp_password"] = temp_pwd
    return out
