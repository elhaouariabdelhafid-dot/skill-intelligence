#!/usr/bin/env bash
# Teste les endpoints principaux avec un vrai jeton.
set -uo pipefail
BASE="http://localhost:8010"

echo "== 1. Santé =="
curl -s "$BASE/api/health"; echo

echo -e "\n== 2. Connexion (RH) =="
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"rh@cmh.ma","password":"Rh@2026"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
if [ -z "${TOKEN:-}" ]; then echo "ÉCHEC login"; exit 1; fi
echo "Jeton obtenu (${#TOKEN} caractères)"

A=(-H "Authorization: Bearer $TOKEN")

echo -e "\n== 3. /auth/me =="
curl -s "${A[@]}" "$BASE/auth/me"; echo

echo -e "\n== 4. /api/people =="
curl -s "${A[@]}" "$BASE/api/people" | head -c 400; echo

echo -e "\n== 5. /api/evaluations =="
curl -s "${A[@]}" "$BASE/api/evaluations?limit=3" | head -c 400; echo

echo -e "\n== 6. /api/questions =="
curl -s "${A[@]}" "$BASE/api/questions" | head -c 300; echo

echo -e "\n== 7. /api/ontology/graph =="
curl -s "${A[@]}" "$BASE/api/ontology/graph" | head -c 300; echo

echo -e "\n== 8. /api/system =="
curl -s "${A[@]}" "$BASE/api/system" | head -c 400; echo

echo -e "\n== 9. Connexion collaborateur + son profil =="
TK=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"hafid@cmh.ma","password":"Hafid@2026"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
curl -s -H "Authorization: Bearer $TK" "$BASE/api/me/profile" | head -c 400; echo

echo -e "\n\n== 10. Contrôle des rôles (collaborateur -> /api/people doit être refusé) =="
curl -s -o /dev/null -w "HTTP %{http_code} (403 attendu)\n" \
  -H "Authorization: Bearer $TK" "$BASE/api/people"

echo -e "\nTests terminés."
