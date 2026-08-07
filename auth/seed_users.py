"""Crée des comptes de démonstration, un par rôle, avec mots de passe hashés.

À lancer une fois pour peupler la base d'utilisateurs de test.
Les mots de passe sont hashés avant stockage.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from auth.auth_models import AuthUser, Organization, Role, get_auth_session
from auth.security import hash_password

# Comptes de démo (email, mot de passe, nom, rôle)
DEMO_USERS = [
    ("admin@cmh.ma",       "Admin@2026",    "Administrateur Système", Role.ADMIN),
    ("rh@cmh.ma",          "Rh@2026",       "Responsable RH",         Role.RH),
    ("manager@cmh.ma",     "Manager@2026",  "Chef d'équipe",          Role.MANAGER),
    ("formateur@cmh.ma",   "Formateur@2026","Formateur AWS",          Role.FORMATEUR),
    ("hafid@cmh.ma",       "Hafid@2026",    "Abdelhafid",             Role.COLLABORATEUR),
]


def seed():
    session = get_auth_session()

    # Organisation par défaut
    org = session.query(Organization).filter(Organization.name == "CMH").first()
    if not org:
        org = Organization(name="CMH")
        session.add(org); session.commit()
        print(f"Organisation créée : CMH (id={org.id})")

    created = 0
    for email, pwd, name, role in DEMO_USERS:
        if session.query(AuthUser).filter(AuthUser.email == email).first():
            print(f"  {email} existe déjà, ignoré")
            continue
        user = AuthUser(
            email=email,
            password_hash=hash_password(pwd),
            full_name=name,
            role=role.value,
            org_id=org.id,
        )
        session.add(user); session.commit()
        created += 1
        print(f"  Créé : {email} / {pwd}  (rôle : {role.value})")

    session.close()
    print(f"\n{created} comptes créés.")
    print("\n=== IDENTIFIANTS DE DÉMONSTRATION ===")
    for email, pwd, name, role in DEMO_USERS:
        print(f"  {role.value:14} → {email}  /  {pwd}")


if __name__ == "__main__":
    seed()
