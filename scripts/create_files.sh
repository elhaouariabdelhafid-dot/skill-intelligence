#!/usr/bin/env bash
# ============================================================
# Crée l'arborescence complète du projet (Phases 1 à 7)
# Usage :  bash scripts/create_files.sh
# Idempotent : ne écrase aucun fichier existant.
# ============================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> Création des répertoires"
mkdir -p \
  llm \
  ingestion \
  retrieval \
  generation \
  agents \
  skills \
  db \
  api \
  frontend \
  core \
  evaluation/results \
  scripts \
  data/raw \
  data/processed \
  data/reference/exam_guides \
  data/reference/sample_questions \
  notebooks \
  volumes

echo "==> Création des __init__.py"
for pkg in llm ingestion retrieval generation agents skills db api core evaluation; do
  [[ -f "$pkg/__init__.py" ]] || touch "$pkg/__init__.py"
done

echo "==> Placeholders des phases futures"
declare -A FUTURE=(
  ["agents/state.py"]="Phase 4 — état partagé LangGraph (TypedDict)"
  ["agents/grader.py"]="Phase 4 — agent Retriever-Grader"
  ["agents/reasoner.py"]="Phase 4 — agent Reasoning Evaluator"
  ["agents/critic.py"]="Phase 4 — agent Critic-Verifier"
  ["agents/aggregator.py"]="Phase 4 — agrégation pondérée + feedback"
  ["agents/graph.py"]="Phase 4 — assemblage du graphe LangGraph"
  ["evaluation/human_correlation.py"]="Phase 5 — Spearman + Krippendorff alpha"
  ["skills/ontology.py"]="Phase 6 — ontologie de compétences Neo4j"
  ["skills/profile.py"]="Phase 6 — agrégation des scores par compétence"
  ["db/models.py"]="Phase 6 — modèles SQLAlchemy"
  ["db/session.py"]="Phase 6 — session PostgreSQL"
  ["api/main.py"]="Phase 6 — endpoints FastAPI"
  ["frontend/app.py"]="Phase 6 — dashboard Streamlit"
)
for f in "${!FUTURE[@]}"; do
  if [[ ! -f "$f" ]]; then
    printf '"""%s — à implémenter."""\n' "${FUTURE[$f]}" > "$f"
    echo "    créé : $f"
  fi
done

echo "==> Fichiers de données vides"
[[ -f data/processed/.gitkeep ]] || touch data/processed/.gitkeep
[[ -f data/reference/sample_questions/README.txt ]] || cat > data/reference/sample_questions/README.txt << 'TXT'
ATTENTION : les questions officielles d'examen AWS placées ici servent
UNIQUEMENT au calibrage de la difficulté (Phase 3) et à la comparaison
en Phase 5.

Elles ne doivent JAMAIS être indexées dans Qdrant : le répertoire
data/reference/ est volontairement exclu de ingestion/loaders.py, qui ne
parcourt que data/raw/. Ne déplace pas ces fichiers.
TXT

echo ""
echo "Arborescence prête :"
find . -maxdepth 2 -type d -not -path './.git*' -not -path './.venv*' \
  -not -path './volumes*' -not -path './data/*' | sort
