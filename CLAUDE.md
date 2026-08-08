# CLAUDE.md — contexte projet

## Projet

**AI Skill Intelligence Platform** (PFA CMH) — évaluation automatisée des
compétences Cloud AWS par RAG hybride et agents LLM.
Pipeline : ingestion → retrieval → génération de questions → évaluation
multi-agents → profil de compétences et recommandations.

La structure des dossiers est décrite dans `STRUCTURE.md`. **La lire avant de
créer un fichier.**

## Environnement

- WSL Ubuntu, Docker Desktop (Windows), VS Code
- Environnement virtuel : `source .venv/bin/activate`
- Racine du projet : `~/skill-intelligence`

## Commandes

```bash
make up            # démarrer Qdrant, PostgreSQL, Ollama
make api           # API FastAPI (port 8000)
make web           # interface React (Vite)
make dashboard     # tableau de bord Streamlit (port 8501)
make test          # tests de régression
make clean         # nettoyer les caches Python
```

## Conventions

- **Fournir les fichiers complets**, jamais des diffs partiels ni des
  remplacements de lignes ciblés : les éditions partielles ont déjà provoqué
  des balises JSX non appariées lors des copier-coller.
- **Aucun fichier `.bak`.** L'historique est géré par git.
- **La racine ne contient que de la configuration** — pas de script, de log,
  de CSV ni d'archive.
- Les tests vivent dans `tests/`, les utilitaires dans `scripts/`.
- Les données lourdes ne sont pas versionnées : `data/`, `volumes/`, `logs/`,
  `archive/`.

## Pièges connus

- `pymysql` exige le paquet `cryptography` pour l'authentification.
- `bcrypt` 4.1+ est incompatible avec `passlib` 1.7.4 → épingler `bcrypt==4.0.1`.
- L'ordre de démarrage Docker doit passer par des `healthcheck` avec
  `condition: service_healthy`, pas par un simple `depends_on`.
- TypeScript : rôle potentiellement `null` utilisé comme index (`Sidebar.tsx`),
  assertions non-null sur un `user` possiblement nul, propriété `phone`
  manquante sur `AuthUser` (`Settings.tsx`).
- `data/reference/` ne doit **jamais** être indexé dans Qdrant :
  `ingestion/loaders.py` ne parcourt que `data/raw/`.

## Deux interfaces distinctes

- `frontend-web/` — React + Vite, interface utilisateur (étudiants, enseignants)
- `dashboard/` — Streamlit, tableau de bord RH (Phase 7)
