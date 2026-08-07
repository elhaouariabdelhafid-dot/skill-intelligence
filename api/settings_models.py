"""Paramètres applicatifs modifiables par l'administrateur.

POURQUOI EN BASE plutôt que dans .env : ces réglages relèvent de l'exploitation
courante (seuil de compétence, pondérations, modèle utilisé). Les changer ne doit
pas demander de redémarrer le service ni d'éditer un fichier sur le serveur.

Le .env garde ce qui est structurel : URLs des bases, clés d'API, secrets.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class CBase(DeclarativeBase):
    pass


class AppSetting(CBase):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(CBase):
    """Trace des actions d'administration — exigence de conformité courante."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Valeurs par défaut et métadonnées d'affichage
DEFAULTS = {
    "skill_threshold":  {"value": "60", "type": "number", "min": 0, "max": 100,
                         "label": "Seuil de maîtrise (%)",
                         "help": "En dessous, une compétence est considérée comme à renforcer."},
    "weight_grader":    {"value": "0.45", "type": "number", "min": 0, "max": 1, "step": 0.05,
                         "label": "Pondération — exactitude",
                         "help": "Poids de l'agent Grader dans le score final."},
    "weight_reasoner":  {"value": "0.45", "type": "number", "min": 0, "max": 1, "step": 0.05,
                         "label": "Pondération — raisonnement",
                         "help": "Poids de l'agent Reasoner dans le score final."},
    "weight_critic":    {"value": "0.10", "type": "number", "min": 0, "max": 1, "step": 0.05,
                         "label": "Pondération — vérification",
                         "help": "Poids de l'agent Critic dans le score final."},
    "veto_cap":         {"value": "1.5", "type": "number", "min": 0, "max": 4, "step": 0.1,
                         "label": "Plafond en cas d'hallucination",
                         "help": "Score maximal si le Critic détecte une hallucination majeure."},
    "llm_provider":     {"value": "groq", "type": "select",
                         "options": ["groq", "ollama", "gemini", "cerebras"],
                         "label": "Fournisseur LLM",
                         "help": "Distant (rapide) ou local (souverain, sans quota)."},
    "llm_model":        {"value": "llama-3.1-8b-instant", "type": "text",
                         "label": "Modèle",
                         "help": "Identifiant du modèle chez le fournisseur choisi."},
    "retrieval_top_k":  {"value": "5", "type": "number", "min": 1, "max": 20,
                         "label": "Passages récupérés",
                         "help": "Nombre de fragments fournis aux agents comme contexte."},
}


_engine = None
_Session = None


def get_settings_db():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=False)
        CBase.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine)
    return _Session()


def get_setting(key: str, fallback=None):
    """Lit un paramètre, avec repli sur la valeur par défaut."""
    db = get_settings_db()
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    db.close()
    if row is not None:
        return row.value
    if fallback is not None:
        return fallback
    return DEFAULTS.get(key, {}).get("value")


def get_float(key: str) -> float:
    try:
        return float(get_setting(key))
    except (TypeError, ValueError):
        return float(DEFAULTS.get(key, {}).get("value", 0))


def log_action(actor: str, action: str, detail: str = ""):
    db = get_settings_db()
    db.add(AuditLog(actor=actor, action=action, detail=detail))
    db.commit(); db.close()
