"""Expose les parametres d'affichage a l'interface, sans authentification.

POURQUOI UN ENDPOINT DEDIE : le frontend a besoin du seuil de maitrise des le
chargement, pour colorer les niveaux et decider ce qui constitue une lacune.
La liste complete des parametres est reservee a l'administrateur ; seul le
seuil, qui n'est pas une donnee sensible, est expose a tous les roles.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/public")
def public_config():
    """Parametres necessaires a l'affichage, lisibles par tous."""
    try:
        from api.settings_models import get_float
        threshold = get_float("skill_threshold")
    except Exception:
        threshold = 60.0
    return {"skill_threshold": threshold}
