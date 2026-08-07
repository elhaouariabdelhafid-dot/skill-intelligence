#!/usr/bin/env bash
# ============================================================================
#  reorganize.sh — Réorganisation & nettoyage du projet skill-intelligence
#
#  USAGE :
#     bash reorganize.sh            # DRY-RUN : affiche ce qui serait fait
#     bash reorganize.sh --apply    # applique réellement les changements
#
#  Idempotent : le relancer ne casse rien.
#  Aucun code source n'est supprimé. Tout est DÉPLACÉ vers archive/ (récupérable).
#  Seuls les caches Python et les dossiers vides sont réellement supprimés.
# ============================================================================

set -uo pipefail

ROOT="${PROJECT_ROOT:-$HOME/skill-intelligence}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

cd "$ROOT" || { echo "Dossier introuvable : $ROOT"; exit 1; }

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_HEAD=$'\033[1;36m'; C_OFF=$'\033[0m'
MOVED=0; DELETED=0; SKIPPED=0

say()   { printf '%s\n' "$*"; }
head_() { printf '\n%s==> %s%s\n' "$C_HEAD" "$*" "$C_OFF"; }

run() {
  if [ "$APPLY" -eq 1 ]; then
    "$@"
  else
    printf '  %s[dry]%s' "$C_WARN" "$C_OFF"; printf ' %q' "$@"; printf '\n'
  fi
}

# Déplace src -> dstdir en gérant les collisions de noms
move_to() {
  local src="$1" dstdir="$2"
  [ -e "$src" ] || { SKIPPED=$((SKIPPED+1)); return 0; }
  local base; base="$(basename "$src")"
  local dst="$dstdir/$base"
  [ -e "$dst" ] && dst="$dstdir/${base}.$(date +%s)"
  run mkdir -p "$dstdir"
  run mv -- "$src" "$dst"
  MOVED=$((MOVED+1))
}

# Chemins exclus de tous les parcours find
PRUNE=( -name .git -prune -o -name .venv -prune -o -name node_modules -prune
        -o -name volumes -prune -o -name archive -prune -o )

say "${C_HEAD}Projet : $ROOT${C_OFF}"
if [ "$APPLY" -eq 1 ]; then
  say "${C_OK}MODE : APPLICATION RÉELLE${C_OFF}"
else
  say "${C_WARN}MODE : DRY-RUN (rien ne sera modifié).${C_OFF}"
fi

# ---------------------------------------------------------------------------
# 0. Sauvegarde git avant toute manipulation
# ---------------------------------------------------------------------------
head_ "0. Sauvegarde git"
if [ -d .git ]; then
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    say "  Modifications non commitées détectées -> commit de sécurité."
    run git add -A
    run git commit -m "chore: snapshot avant reorganisation" --no-verify
  else
    say "  Arbre de travail propre."
  fi
  say "  Branche courante : $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  if git rev-parse --verify chore/reorg >/dev/null 2>&1; then
    say "  Branche chore/reorg déjà existante."
  else
    run git checkout -b chore/reorg
  fi
else
  say "  ${C_WARN}Pas de dépôt git — aucune sauvegarde automatique.${C_OFF}"
fi

# ---------------------------------------------------------------------------
# 1. Arborescence cible
# ---------------------------------------------------------------------------
head_ "1. Création des dossiers cibles"
for d in archive/packages archive/backups archive/legacy tests logs data/forms; do
  say "  mkdir -p $d"
  run mkdir -p "$d"
done

# ---------------------------------------------------------------------------
# 2. Les 26 archives .zip de la racine -> archive/packages/
# ---------------------------------------------------------------------------
head_ "2. Archives .zip de la racine -> archive/packages/"
shopt -s nullglob
for z in ./*.zip; do
  say "  ${z#./}"
  move_to "$z" "archive/packages"
done
shopt -u nullglob

# ---------------------------------------------------------------------------
# 3. Fichiers .bak / .bakN -> archive/backups/ (arborescence préservée)
# ---------------------------------------------------------------------------
head_ "3. Sauvegardes (.bak, .bak2 … .bak11, *~, *.orig) -> archive/backups/"
while IFS= read -r -d '' f; do
  rel="${f#./}"
  dest="archive/backups/$(dirname "$rel")"
  say "  $rel"
  run mkdir -p "$dest"
  run mv -- "$f" "$dest/$(basename "$rel")"
  MOVED=$((MOVED+1))
done < <(find . "${PRUNE[@]}" \
  -type f \( -name '*.bak' -o -name '*.bak[0-9]*' -o -name '*~' -o -name '*.orig' \) -print0)

if [ -d .backup ]; then
  say "  .backup/ -> archive/backups/_dot_backup/"
  run mkdir -p archive/backups/_dot_backup
  shopt -s nullglob dotglob
  for f in .backup/*; do run mv -- "$f" archive/backups/_dot_backup/; MOVED=$((MOVED+1)); done
  shopt -u nullglob dotglob
  [ "$APPLY" -eq 1 ] && rmdir .backup 2>/dev/null
fi

# ---------------------------------------------------------------------------
# 4. Caches Python (régénérés automatiquement)
# ---------------------------------------------------------------------------
head_ "4. Suppression des caches Python"
while IFS= read -r -d '' d; do
  say "  rm -rf ${d#./}"
  run rm -rf -- "$d"
  DELETED=$((DELETED+1))
done < <(find . -name .git -prune -o -name .venv -prune -o -name node_modules -prune -o \
  -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.ruff_cache' \) -print0)

# ---------------------------------------------------------------------------
# 5. Dossier fantôme : data/{raw,processed,reference/{...}}
#    (créé par une expansion de braces ratée, probablement create_files.sh)
# ---------------------------------------------------------------------------
head_ "5. Dossier fantôme (bug d'expansion de braces)"
GHOST='data/{raw,processed,reference'
if [ -d "$GHOST" ]; then
  if [ -z "$(find "$GHOST" -type f -print -quit)" ]; then
    say "  Vide -> suppression"
    run rm -rf -- "$GHOST"
    DELETED=$((DELETED+1))
  else
    say "  ${C_WARN}Contient des fichiers -> archive/legacy/ pour inspection${C_OFF}"
    run mkdir -p archive/legacy
    run mv -- "$GHOST" "archive/legacy/ghost_braces_dir"
    MOVED=$((MOVED+1))
  fi
else
  say "  Déjà absent."
fi

# ---------------------------------------------------------------------------
# 6. Logs & résultats bruts -> logs/
# ---------------------------------------------------------------------------
head_ "6. Logs et résultats -> logs/"
for f in ragas_final.log ragas_v2.log resultats_ragas_final.txt variance_agents.json; do
  [ -e "$f" ] && say "  $f"
  move_to "$f" "logs"
done

# ---------------------------------------------------------------------------
# 7. CSV de la racine -> data/forms/
# ---------------------------------------------------------------------------
head_ "7. Données CSV -> data/forms/"
for f in reponses.csv nouveaux_repondants.csv; do
  [ -e "$f" ] && say "  $f"
  move_to "$f" "data/forms"
done

# ---------------------------------------------------------------------------
# 8. Utilitaires de la racine -> scripts/
# ---------------------------------------------------------------------------
head_ "8. Utilitaires -> scripts/"
for f in export_forms.py import_forms.py download_corpus.sh; do
  [ -e "$f" ] && say "  $f"
  move_to "$f" "scripts"
done

# ---------------------------------------------------------------------------
# 9. Séparation tests / scripts
# ---------------------------------------------------------------------------
head_ "9. Tests -> tests/"
shopt -s nullglob
for f in scripts/test_*.py scripts/test_*.sh agents/test_*.py; do
  say "  $f"
  move_to "$f" "tests"
done
shopt -u nullglob

# ---------------------------------------------------------------------------
# 10. Ancien frontend Streamlit -> archive/legacy/
#     (le frontend actif est frontend-web/, React + Vite)
# ---------------------------------------------------------------------------
head_ "10. Ancien frontend Streamlit -> archive/legacy/streamlit/"
if [ -d frontend ] && [ ! -d frontend/src ]; then
  say "  frontend/ (app.py) -> archive/legacy/streamlit/"
  run mkdir -p archive/legacy
  run mv -- frontend archive/legacy/streamlit
  MOVED=$((MOVED+1))
else
  say "  Rien à faire."
fi

# ---------------------------------------------------------------------------
# 11. Dossiers vides résiduels
# ---------------------------------------------------------------------------
head_ "11. Dossiers vides"
while IFS= read -r -d '' d; do
  say "  rmdir ${d#./}"
  run rmdir -- "$d"
done < <(find . -name .git -prune -o -name .venv -prune -o -name node_modules -prune -o \
  -name volumes -prune -o -name notebooks -prune -o -path ./data -prune -o \
  -type d -empty -print0)

# ---------------------------------------------------------------------------
# 12. Rapport
# ---------------------------------------------------------------------------
head_ "Résumé"
say "  Déplacés  : $MOVED"
say "  Supprimés : $DELETED"
say "  Ignorés   : $SKIPPED (déjà absents)"

say ""
if [ "$APPLY" -eq 1 ]; then
  say "${C_OK}Terminé.${C_OFF} Vérifiez :"
  say "  tree -L 2 -I 'node_modules|__pycache__|.git|.venv|volumes'"
  say "  git status"
  say ""
  say "Valider  : git add -A && git commit -m 'chore: reorganisation du projet'"
  say "Annuler  : git checkout - && git branch -D chore/reorg"
else
  say "${C_WARN}Aucune modification.${C_OFF} Pour exécuter :  bash reorganize.sh --apply"
fi
