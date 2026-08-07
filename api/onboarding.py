"""Arrivees de collaborateurs — creation conjointe compte + profil metier.

LE PROBLEME RESOLU : la table auth_users (connexion) et la table users
(evaluations) sont distinctes. Creer un compte sans profil metier produit un
utilisateur invisible : il ne peut ni etre invite a une session, ni voir son
espace. Ce module cree les deux et etablit la liaison.

QUI FAIT QUOI :
  RH    declare les arrivees de collaborateurs (son metier)
  ADMIN cree les comptes a role eleve et traite les cas particuliers
"""
from __future__ import annotations

import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from auth.auth_api import require_role
from auth.auth_models import AuthUser, Organization, Role, get_auth_session
from auth.security import hash_password
from db.models import User, get_session
from api.settings_models import log_action

router = APIRouter(prefix="/api/staff", tags=["onboarding"])


class NewMemberIn(BaseModel):
    full_name: str
    email: EmailStr
    role: str = "collaborateur"
    team: str = ""


def temp_password(n: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n)) + "!7"


def create_member(full_name: str, email: str, role: str, actor: str,
                  password: str | None = None) -> dict:
    """Cree le compte de connexion ET le profil metier, puis les relie.

    Reutilisable depuis l'onboarding RH et depuis l'approbation d'une demande
    d'acces, pour garantir le meme resultat par les deux chemins.
    """
    email = email.strip().lower()
    full_name = full_name.strip()

    if role not in [r.value for r in Role]:
        raise HTTPException(400, "Role invalide")

    asess = get_auth_session()
    if asess.query(AuthUser).filter(AuthUser.email == email).first():
        asess.close()
        raise HTTPException(400, "Un compte existe deja pour cette adresse")

    org = asess.query(Organization).filter(Organization.name == "CMH").first()
    if not org:
        org = Organization(name="CMH")
        asess.add(org); asess.commit()

    # Profil metier : necessaire pour etre evaluable et selectionnable
    profile_id = None
    core = get_session()
    existing = core.query(User).filter(User.name == full_name).first()
    if existing:
        profile_id = existing.id          # rattachement a un profil deja evalue
    else:
        u = User(name=full_name, role=role)
        core.add(u); core.commit()
        profile_id = u.id
    core.close()

    pwd = password or temp_password()
    account = AuthUser(email=email, password_hash=hash_password(pwd),
                       full_name=full_name, role=role, org_id=org.id,
                       profile_user_id=profile_id)
    asess.add(account); asess.commit()
    account_id = account.id
    asess.close()

    log_action(actor, "arrivee de collaborateur",
               f"{email} · role {role} · profil metier #{profile_id}")

    return {"account_id": account_id, "profile_user_id": profile_id,
            "email": email, "full_name": full_name, "role": role,
            "temp_password": pwd, "linked_existing": bool(existing)}


@router.post("/onboard")
def onboard(data: NewMemberIn, user: dict = Depends(require_role("rh", "admin"))):
    """Declare l'arrivee d'un collaborateur : compte + profil en une operation.

    Le RH ne peut declarer que des collaborateurs ; les roles a privileges
    relevent de l'administrateur.
    """
    if user["role"] == "rh" and data.role != "collaborateur":
        raise HTTPException(403,
            "Les roles a privileges sont crees par l'administrateur")
    return create_member(data.full_name, data.email, data.role, user["email"])


@router.get("/unlinked")
def unlinked(user: dict = Depends(require_role("rh", "admin"))):
    """Comptes sans profil metier — anomalies heritees, a reparer."""
    asess = get_auth_session()
    rows = asess.query(AuthUser).filter(
        AuthUser.role == "collaborateur",
        AuthUser.profile_user_id.is_(None)).all()
    out = [{"id": a.id, "email": a.email, "full_name": a.full_name} for a in rows]
    asess.close()
    return out


@router.post("/{account_id}/link")
def repair_link(account_id: int, user: dict = Depends(require_role("rh", "admin"))):
    """Cree le profil metier manquant d'un compte existant."""
    asess = get_auth_session()
    a = asess.query(AuthUser).filter(AuthUser.id == account_id).first()
    if a is None:
        asess.close(); raise HTTPException(404, "Compte introuvable")
    if a.profile_user_id:
        asess.close(); raise HTTPException(400, "Ce compte a deja un profil")

    core = get_session()
    existing = core.query(User).filter(User.name == a.full_name).first()
    if existing:
        pid = existing.id
    else:
        u = User(name=a.full_name, role=a.role)
        core.add(u); core.commit()
        pid = u.id
    core.close()

    a.profile_user_id = pid
    asess.commit()
    out = {"account_id": account_id, "profile_user_id": pid, "repaired": True}
    asess.close()
    log_action(user["email"], "reparation de liaison", f"{a.email} -> profil #{pid}")
    return out
