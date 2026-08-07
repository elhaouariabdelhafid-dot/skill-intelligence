"""Relie chaque compte d'authentification à son profil métier.

POURQUOI : la table auth_users (login) et la table users (évaluations) sont
distinctes. Le champ profile_user_id fait le pont, pour qu'un collaborateur
connecté voie SON profil.

Le rapprochement se fait par nom, avec possibilité de forcer manuellement.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from auth.auth_models import AuthUser, get_auth_session
from db.models import User, get_session

# Rapprochements manuels : email du compte -> id dans la table users
MANUAL = {
    "hafid@cmh.ma": 4,
}


def link():
    asess = get_auth_session()
    dsess = get_session()
    business = {u.name.strip().lower(): u.id for u in dsess.query(User).all()}
    print("Profils métier disponibles :")
    for name, uid in business.items():
        print(f"  id={uid:<3} {name}")

    linked = 0
    for au in asess.query(AuthUser).all():
        target = MANUAL.get(au.email)
        if target is None:
            key = au.full_name.strip().lower()
            target = business.get(key)
        if target is None:
            print(f"  — {au.email} : aucun profil métier correspondant (normal pour RH/admin)")
            continue
        au.profile_user_id = target
        asess.commit()
        linked += 1
        print(f"  ✓ {au.email} → profil métier id={target}")

    asess.close(); dsess.close()
    print(f"\n{linked} compte(s) relié(s).")


if __name__ == "__main__":
    link()
