"""Fonctions de sécurité — hashage bcrypt + tokens JWT.

HASHAGE : bibliothèque bcrypt directement (plus robuste que passlib qui a des
soucis de compatibilité de version). bcrypt est à sens unique et intègre un sel
aléatoire par mot de passe.

JWT : jeton signé contenant l'identité et le rôle. Signé avec une clé secrète,
impossible à falsifier. Expire après un délai.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

import bcrypt
from jose import JWTError, jwt

JWT_SECRET = getattr(settings, "jwt_secret", "change-me-in-production-please")
JWT_ALGO = "HS256"
JWT_EXPIRE_HOURS = 12


def hash_password(plain: str) -> str:
    """Hash bcrypt d'un mot de passe. bcrypt limite à 72 octets, on tronque."""
    pwd_bytes = plain.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash bcrypt."""
    try:
        pwd_bytes = plain.encode("utf-8")[:72]
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, email: str, role: str, org_id: int) -> str:
    """Génère un JWT signé contenant l'identité et le rôle."""
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "org_id": org_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_access_token(token: str) -> dict | None:
    """Vérifie et décode un JWT. Retourne le payload ou None si invalide/expiré."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError:
        return None
