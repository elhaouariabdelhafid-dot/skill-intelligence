"""Endpoints du circuit de demandes d'évaluation.

MANAGER    : crée une demande pour son équipe, suit son avancement
RH         : consulte la file, valide ou refuse avec commentaire
FORMATEUR  : voit les demandes validées, les transforme en session d'examen

Le lien avec les sessions : quand le formateur planifie une demande validée,
une session est créée avec les mêmes services et participants, et la demande
passe à « planifiée » en conservant l'identifiant de session.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.auth_api import get_current_user, require_role
from db.models import User, get_session
from api.requests_models import EvalRequest, get_requests_db
from api.sessions_models import EvalSession, get_sessions_db

router = APIRouter(prefix="/api/requests", tags=["requests"])


class RequestIn(BaseModel):
    title: str
    justification: str = ""
    services: list[str] = []
    participants: list[int] = []
    priority: str = "normale"


class ReviewIn(BaseModel):
    decision: str            # "validée" ou "refusée"
    comment: str = ""


def _serialize(r: EvalRequest, names: dict) -> dict:
    return {
        "id": r.id, "title": r.title, "justification": r.justification,
        "services": r.services, "priority": r.priority, "status": r.status,
        "participants": [{"id": p, "name": names.get(p, f"User {p}")} for p in (r.participants or [])],
        "requested_by": r.requested_by, "requester_name": r.requester_name,
        "reviewed_by": r.reviewed_by, "review_comment": r.review_comment,
        "reviewed_at": r.reviewed_at.strftime("%d/%m/%Y %H:%M") if r.reviewed_at else None,
        "session_id": r.session_id,
        "created_at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else None,
    }


def _names() -> dict:
    s = get_session()
    out = {u.id: u.name for u in s.query(User).all()}
    s.close()
    return out


# ══════════════ manager ══════════════
@router.post("")
def create_request(data: RequestIn,
                   user: dict = Depends(require_role("manager", "admin"))):
    """Le manager soumet un besoin d'évaluation pour son équipe."""
    if not data.title.strip():
        raise HTTPException(400, "Donnez un intitulé à la demande")
    if not data.participants:
        raise HTTPException(400, "Sélectionnez au moins un collaborateur")

    db = get_requests_db()
    r = EvalRequest(
        requested_by=user["email"],
        requester_name=user.get("email", "").split("@")[0],
        title=data.title, justification=data.justification,
        services=data.services, participants=data.participants,
        priority=data.priority, status="en_attente")
    db.add(r); db.commit()
    out = _serialize(r, _names())
    db.close()
    return out


@router.get("/mine")
def my_requests(user: dict = Depends(require_role("manager", "admin"))):
    """Demandes soumises par le manager connecté."""
    db = get_requests_db()
    rows = (db.query(EvalRequest).filter(EvalRequest.requested_by == user["email"])
            .order_by(EvalRequest.id.desc()).all())
    names = _names()
    out = [_serialize(r, names) for r in rows]
    db.close()
    return out


# ══════════════ RH ══════════════
@router.get("")
def list_requests(status: str | None = None,
                  user: dict = Depends(require_role("rh", "admin", "formateur"))):
    """File des demandes. Le formateur ne voit que celles qui sont validées."""
    db = get_requests_db()
    q = db.query(EvalRequest)
    if status:
        q = q.filter(EvalRequest.status == status)
    elif user["role"] == "formateur":
        q = q.filter(EvalRequest.status.in_(["validée", "planifiée"]))
    rows = q.order_by(EvalRequest.id.desc()).all()
    names = _names()
    out = [_serialize(r, names) for r in rows]
    db.close()
    return out


@router.post("/{rid}/review")
def review_request(rid: int, data: ReviewIn,
                   user: dict = Depends(require_role("rh", "admin"))):
    """Le RH arbitre : valide ou refuse, avec un motif."""
    if data.decision not in ("validée", "refusée"):
        raise HTTPException(400, "Décision invalide (validée ou refusée)")

    db = get_requests_db()
    r = db.query(EvalRequest).filter(EvalRequest.id == rid).first()
    if r is None:
        db.close(); raise HTTPException(404, "Demande introuvable")
    if r.status != "en_attente":
        db.close(); raise HTTPException(400, f"Demande déjà traitée (statut : {r.status})")

    r.status = data.decision
    r.reviewed_by = user["email"]
    r.review_comment = data.comment
    r.reviewed_at = datetime.utcnow()
    db.commit()
    out = _serialize(r, _names())
    db.close()
    return out


# ══════════════ formateur ══════════════
@router.post("/{rid}/plan")
def plan_request(rid: int, user: dict = Depends(require_role("formateur", "admin"))):
    """Transforme une demande validée en session d'évaluation."""
    db = get_requests_db()
    r = db.query(EvalRequest).filter(EvalRequest.id == rid).first()
    if r is None:
        db.close(); raise HTTPException(404, "Demande introuvable")
    if r.status != "validée":
        db.close(); raise HTTPException(400,
            f"Seules les demandes validées peuvent être planifiées (statut : {r.status})")

    sdb = get_sessions_db()
    s = EvalSession(title=r.title, created_by=user["email"],
                    services=r.services, participants=r.participants,
                    status="brouillon", message=f"Issue de la demande #{r.id}")
    sdb.add(s); sdb.commit()
    sid = s.id
    sdb.close()

    r.session_id = sid
    r.status = "planifiée"
    db.commit()
    out = _serialize(r, _names())
    db.close()
    return out


# ══════════════ synthèse ══════════════
@router.get("/summary")
def summary(user: dict = Depends(require_role("rh", "admin", "manager", "formateur"))):
    """Compteurs par statut, pour les tuiles de tableau de bord."""
    db = get_requests_db()
    rows = db.query(EvalRequest).all()
    db.close()
    counts = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"total": len(rows), "by_status": counts}
