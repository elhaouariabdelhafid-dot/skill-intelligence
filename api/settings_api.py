"""Endpoints d'administration technique.

PERIMETRE DE L'ADMINISTRATEUR : il gere l'outil, pas les competences.
Comptes, parametres, etat des services, corpus, journal d'audit. Il n'arbitre
aucune demande de formation et ne consulte pas les profils individuels —
principe de separation des responsabilites.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.auth_api import require_role
from api.settings_models import (DEFAULTS, AppSetting, AuditLog,
                                 get_float, get_settings_db, log_action)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SettingIn(BaseModel):
    key: str
    value: str


@router.get("/settings")
def list_settings(user: dict = Depends(require_role("admin"))):
    """Parametres courants, fusionnes avec leurs metadonnees d'affichage."""
    db = get_settings_db()
    stored = {r.key: r for r in db.query(AppSetting).all()}
    db.close()
    out = []
    for key, meta in DEFAULTS.items():
        row = stored.get(key)
        out.append({
            "key": key,
            "value": row.value if row else meta["value"],
            "default": meta["value"],
            "modified": row is not None and row.value != meta["value"],
            "label": meta["label"],
            "help": meta["help"],
            "type": meta["type"],
            "options": meta.get("options"),
            "min": meta.get("min"),
            "max": meta.get("max"),
            "step": meta.get("step"),
            "updated_by": row.updated_by if row else None,
            "updated_at": (row.updated_at.strftime("%d/%m/%Y %H:%M")
                           if row and row.updated_at else None),
        })
    return out


@router.put("/settings")
def update_setting(data: SettingIn, user: dict = Depends(require_role("admin"))):
    """Modifie un parametre. Les valeurs sont controlees avant enregistrement."""
    if data.key not in DEFAULTS:
        raise HTTPException(400, f"Parametre inconnu : {data.key}")

    meta = DEFAULTS[data.key]
    if meta["type"] == "number":
        try:
            v = float(data.value)
        except ValueError:
            raise HTTPException(400, "Valeur numerique attendue")
        if meta.get("min") is not None and v < meta["min"]:
            raise HTTPException(400, f"Minimum : {meta['min']}")
        if meta.get("max") is not None and v > meta["max"]:
            raise HTTPException(400, f"Maximum : {meta['max']}")
    if meta["type"] == "select" and data.value not in meta.get("options", []):
        raise HTTPException(400, f"Valeur autorisee : {', '.join(meta['options'])}")

    db = get_settings_db()
    row = db.query(AppSetting).filter(AppSetting.key == data.key).first()
    old = row.value if row else meta["value"]
    if row:
        row.value = data.value
        row.updated_by = user["email"]
        row.updated_at = datetime.utcnow()
    else:
        db.add(AppSetting(key=data.key, value=data.value, updated_by=user["email"]))
    db.commit()
    db.close()

    log_action(user["email"], "modification de parametre",
               f"{data.key} : {old} -> {data.value}")

    # Avertissement si la somme des ponderations s'ecarte de 1
    warning = None
    if data.key.startswith("weight_"):
        total = sum(get_float(k) for k in
                    ("weight_grader", "weight_reasoner", "weight_critic"))
        if abs(total - 1.0) > 0.01:
            warning = (f"La somme des ponderations vaut {total:.2f} — "
                       "elle devrait valoir 1.00.")

    return {"key": data.key, "value": data.value, "warning": warning}


@router.post("/settings/reset")
def reset_settings(user: dict = Depends(require_role("admin"))):
    """Restaure toutes les valeurs par defaut."""
    db = get_settings_db()
    n = db.query(AppSetting).delete()
    db.commit()
    db.close()
    log_action(user["email"], "reinitialisation", f"{n} parametre(s) restaure(s)")
    return {"reset": n}


@router.get("/audit")
def audit(limit: int = 40, user: dict = Depends(require_role("admin"))):
    """Journal des actions d'administration."""
    db = get_settings_db()
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    out = [{"id": r.id, "actor": r.actor, "action": r.action, "detail": r.detail,
            "at": r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else None}
           for r in rows]
    db.close()
    return out


@router.get("/corpus")
def corpus_info(user: dict = Depends(require_role("admin"))):
    """Etat du corpus documentaire indexe."""
    from config import settings as cfg
    info = {"embedding": cfg.embedding_model, "collection": cfg.qdrant_collection}
    try:
        from qdrant_client import QdrantClient
        c = QdrantClient(url=cfg.qdrant_url)
        col = c.get_collection(cfg.qdrant_collection)
        info.update({"points": col.points_count,
                     "vector_size": col.config.params.vectors.size,
                     "status": str(col.status)})
    except Exception as e:
        info["error"] = str(e)[:150]

    chunks = Path(__file__).parent.parent / "data" / "processed" / "chunks.jsonl"
    if chunks.exists():
        info["chunks_file"] = sum(1 for line in chunks.open(encoding="utf-8") if line.strip())
    return info
