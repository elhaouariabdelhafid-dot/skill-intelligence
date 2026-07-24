#!/usr/bin/env bash
# ============================================================
# Phase 0 — Initialisation complète (WSL Ubuntu)
# Usage :  bash scripts/init.sh
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
echo "==> Projet : $PROJECT_DIR"

# ------------------------------------------------------------
# 1. Vérifications préalables
# ------------------------------------------------------------
command -v docker >/dev/null || { echo "ERREUR : Docker introuvable. Installe Docker Desktop et active l'intégration WSL."; exit 1; }
docker compose version >/dev/null || { echo "ERREUR : docker compose v2 requis."; exit 1; }

if [[ "$PROJECT_DIR" == /mnt/c/* ]]; then
  echo "ATTENTION : le projet est sur /mnt/c (filesystem Windows)."
  echo "Déplace-le dans ~/projects/ pour des I/O 10x plus rapides."
fi

# Python 3.11+
PY=python3
if command -v python3.11 >/dev/null; then PY=python3.11; fi
$PY -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ requis"' \
  || { echo "Installe Python 3.11 : sudo apt install python3.11 python3.11-venv"; exit 1; }

# ------------------------------------------------------------
# 2. Environnement Python
# ------------------------------------------------------------
if [[ ! -d .venv ]]; then
  echo "==> Création du venv"
  $PY -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q
echo "==> Installation des dépendances (peut prendre plusieurs minutes : torch)"
pip install -q -r requirements.txt

# ------------------------------------------------------------
# 3. Fichier .env
# ------------------------------------------------------------
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> .env créé depuis .env.example — édite-le pour tes clés API"
fi

# ------------------------------------------------------------
# 4. Démarrage des services Docker
# ------------------------------------------------------------
echo "==> Démarrage des conteneurs"
docker compose up -d qdrant postgres ollama
echo "==> Attente de Qdrant..."
for i in $(seq 1 30); do
  curl -s http://localhost:6333/readyz >/dev/null && break
  sleep 2
done
curl -s http://localhost:6333/readyz >/dev/null \
  && echo "    Qdrant OK  -> http://localhost:6333/dashboard" \
  || { echo "ERREUR : Qdrant ne répond pas"; exit 1; }

# ------------------------------------------------------------
# 5. Modèle LLM local
# ------------------------------------------------------------
echo "==> Téléchargement de Qwen2.5 7B via Ollama (≈4,7 Go, une seule fois)"
docker exec ski-ollama ollama pull qwen2.5:7b
docker exec ski-ollama ollama list

# ------------------------------------------------------------
# 6. Corpus AWS (Phase 1)
# ------------------------------------------------------------
echo "==> Clonage du corpus AWS (dépôts publics awsdocs)"
mkdir -p data/raw
REPOS=(
  aws-well-architected-framework
  amazon-ec2-user-guide
  amazon-s3-userguide
  amazon-vpc-user-guide
  iam-user-guide
  amazon-rds-user-guide
  aws-lambda-developer-guide
)
cd data/raw
for r in "${REPOS[@]}"; do
  if [[ -d "$r" ]]; then
    echo "    $r déjà présent"
  elif git clone --depth 1 "https://github.com/awsdocs/$r.git" 2>/dev/null; then
    echo "    $r OK"
  else
    echo "    $r INDISPONIBLE (dépôt archivé/renommé) — à récupérer manuellement"
  fi
done
cd "$PROJECT_DIR"
echo "==> Fichiers Markdown collectés : $(find data/raw -name '*.md' | wc -l)"

# ------------------------------------------------------------
# 7. Test de bout en bout minimal
# ------------------------------------------------------------
echo "==> Test Ollama"
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen2.5:7b","prompt":"Réponds uniquement: OK","stream":false}' \
  | $PY -c "import sys,json; print('    Ollama répond :', json.load(sys.stdin)['response'][:50])"

echo ""
echo "============================================================"
echo " Phase 0 terminée."
echo " Étapes suivantes :"
echo "   source .venv/bin/activate"
echo "   python ingestion/loaders.py      # vérifier le chargement"
echo "   python ingestion/indexer.py      # indexer le corpus"
echo "   python retrieval/query_naive.py  # premier RAG"
echo "============================================================"
