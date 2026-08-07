"""API d'authentification (FastAPI) — login, register, protection par rôle.

ENDPOINTS :
  POST /auth/register  → créer un compte (mot de passe hashé)
  POST /auth/login     → vérifier identifiants, renvoyer un JWT
  GET  /auth/me        → infos de l'utilisateur connecté (via JWT)

PROTECTION : la dépendance require_role(...) vérifie le JWT ET le rôle avant
d'autoriser l'accès à une route. C'est le RBAC (Role-Based Access Control).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from auth.auth_models import AuthUser, Organization, Role, get_auth_session
from auth.security import (create_access_token, decode_access_token,
                           hash_password, verify_password)

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


# ---- Schémas ----
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = Role.COLLABORATEUR.value
    org_name: str = "CMH"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


# ---- Dépendance : utilisateur courant via JWT ----
def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token manquant")
    payload = decode_access_token(creds.credentials)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalide ou expiré")
    return payload


def require_role(*allowed_roles: str):
    """Fabrique une dépendance qui exige un des rôles autorisés."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Accès réservé aux rôles : {', '.join(allowed_roles)}")
        return user
    return checker


# ---- Endpoints ----
@router.post("/register", response_model=TokenOut)
def register(data: RegisterIn):
    session = get_auth_session()
    # Email déjà pris ?
    if session.query(AuthUser).filter(AuthUser.email == data.email).first():
        session.close()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email déjà enregistré")

    # Organisation (créée si nouvelle)
    org = session.query(Organization).filter(Organization.name == data.org_name).first()
    if not org:
        org = Organization(name=data.org_name)
        session.add(org); session.commit()

    # Rôle valide ?
    if data.role not in [r.value for r in Role]:
        session.close()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rôle invalide")

    user = AuthUser(
        email=data.email,
        password_hash=hash_password(data.password),  # jamais en clair
        full_name=data.full_name,
        role=data.role,
        org_id=org.id,
    )
    session.add(user); session.commit()
    token = create_access_token(user.id, user.email, user.role, user.org_id)
    result = TokenOut(access_token=token, role=user.role, full_name=user.full_name)
    session.close()
    return result


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn):
    session = get_auth_session()
    user = session.query(AuthUser).filter(AuthUser.email == data.email).first()
    if user is None or not verify_password(data.password, user.password_hash):
        session.close()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Email ou mot de passe incorrect")
    token = create_access_token(user.id, user.email, user.role, user.org_id)
    result = TokenOut(access_token=token, role=user.role, full_name=user.full_name)
    session.close()
    return result


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"user_id": user["sub"], "email": user["email"],
            "role": user["role"], "org_id": user["org_id"]}
